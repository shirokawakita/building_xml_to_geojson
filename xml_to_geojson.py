#!/usr/bin/env python3
"""
基盤地図情報の建物データ（-BldA-）をXMLからGeoJSONに変換するスクリプト

使用方法:
    python xml_to_geojson.py <zip_file_path>

例:
    python xml_to_geojson.py 20250918090652709-001.zip
"""

import argparse
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import List, Dict, Any
import xml.etree.ElementTree as ET
from collections import defaultdict


class XMLToGeoJSONConverter:
    """基盤地図情報のXMLをGeoJSONに変換するクラス"""
    
    def __init__(self):
        self.namespaces = {
            'gml': 'http://www.opengis.net/gml/3.2',
            'ksj': 'http://nlftp.mlit.go.jp/ksj/schemas/ksj-app',
            'fme': 'http://www.safe.com/gml/fme'
        }
    
    def parse_coordinates(self, coord_string: str) -> List[List[float]]:
        """座標文字列をパースして座標のリストに変換"""
        if not coord_string:
            return []
        
        # 空白区切りの座標を処理（緯度 経度 緯度 経度 ...）
        coord_parts = coord_string.strip().split()
        coords = []
        
        for i in range(0, len(coord_parts), 2):
            if i + 1 < len(coord_parts):
                # 基盤地図情報では緯度、経度の順で格納されている
                lat = float(coord_parts[i])
                lon = float(coord_parts[i + 1])
                # GeoJSONでは経度、緯度の順なので順序を入れ替え
                coords.append([lon, lat])
        
        return coords
    
    def parse_gml_poslist(self, poslist_element) -> List[List[float]]:
        """GMLのposList要素から座標を取得"""
        coords = []
        if poslist_element is not None:
            text = poslist_element.text
            if text:
                coords = self.parse_coordinates(text)
        return coords
    
    def parse_gml_pos(self, pos_element) -> List[float]:
        """GMLのpos要素から座標を取得"""
        if pos_element is not None and pos_element.text:
            coords = self.parse_coordinates(pos_element.text)
            return coords[0] if coords else []
        return []
    
    def create_geojson_feature(self, building_element, geometry_coords) -> Dict[str, Any]:
        """建物要素からGeoJSONフィーチャーを作成"""
        properties = {}
        
        # 属性情報を取得
        for child in building_element:
            if child.tag.startswith('{') and child.tag.endswith('}'):
                # 名前空間付きタグの場合
                tag_name = child.tag.split('}')[1]
            else:
                tag_name = child.tag
            
            # 建物関連の属性を収集
            if tag_name in ['fid', 'type', 'orgGILvl']:
                properties[tag_name] = child.text
        
        # gml:id属性も取得
        if 'gml:id' in building_element.attrib:
            properties['gml_id'] = building_element.attrib['gml:id']
        
        # 座標が有効な場合のみフィーチャーを作成
        if geometry_coords and len(geometry_coords) >= 3:  # ポリゴンの場合、最低3点必要
            geometry = {
                "type": "Polygon",
                "coordinates": [geometry_coords]
            }
            
            return {
                "type": "Feature",
                "geometry": geometry,
                "properties": properties
            }
        
        return None
    
    def parse_building_xml(self, xml_content: str) -> List[Dict[str, Any]]:
        """建物XMLファイルをパースしてGeoJSONフィーチャーのリストを返す"""
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            print(f"XMLパースエラー: {e}")
            return []
        
        features = []
        
        # 建物要素を検索（BldA要素を直接検索）
        # 名前空間付きで検索
        building_elements = root.findall('.//{http://fgd.gsi.go.jp/spec/2008/FGD_GMLSchema}BldA')
        
        # 各建物要素を処理
        for building in building_elements:
            geometry_coords = []
            
            # gml:posListを検索
            poslist = building.find('.//{http://www.opengis.net/gml/3.2}posList')
            if poslist is not None and poslist.text:
                geometry_coords = self.parse_gml_poslist(poslist)
            
            # フィーチャーを作成
            feature = self.create_geojson_feature(building, geometry_coords)
            if feature:
                features.append(feature)
        
        return features
    
    def extract_and_convert_building_files(self, zip_path: str) -> List[Dict[str, Any]]:
        """ZIPファイルから建物ファイルを抽出してGeoJSONに変換"""
        all_features = []
        
        with zipfile.ZipFile(zip_path, 'r') as main_zip:
            print(f"メインZIPファイルを処理中: {zip_path}")
            
            # メインZIP内のファイル一覧を取得
            file_list = main_zip.namelist()
            zip_files = [f for f in file_list if f.endswith('.zip')]
            
            print(f"見つかったサブZIPファイル数: {len(zip_files)}")
            
            for sub_zip_name in zip_files:
                print(f"処理中: {sub_zip_name}")
                
                # サブZIPファイルを読み込み
                with main_zip.open(sub_zip_name) as sub_zip_data:
                    with zipfile.ZipFile(sub_zip_data, 'r') as sub_zip:
                        # サブZIP内のファイル一覧を取得
                        sub_file_list = sub_zip.namelist()
                        
                        # -BldA-を含むファイルを検索
                        building_files = [f for f in sub_file_list if '-BldA-' in f and f.endswith('.xml')]
                        
                        for building_file in building_files:
                            print(f"  建物ファイル処理中: {building_file}")
                            
                            try:
                                # XMLファイルを読み込み
                                with sub_zip.open(building_file) as xml_data:
                                    xml_content = xml_data.read().decode('utf-8')
                                
                                # XMLをGeoJSONに変換
                                features = self.parse_building_xml(xml_content)
                                all_features.extend(features)
                                
                                print(f"    変換完了: {len(features)}個の建物")
                                
                            except Exception as e:
                                print(f"    エラー: {e}")
                                continue
        
        return all_features


def main():
    parser = argparse.ArgumentParser(description='基盤地図情報の建物データをXMLからGeoJSONに変換')
    parser.add_argument('zip_file', help='基盤地図情報のZIPファイルパス')
    parser.add_argument('-o', '--output', default='buildings.geojson', help='出力ファイル名（デフォルト: buildings.geojson）')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.zip_file):
        print(f"エラー: ファイルが見つかりません: {args.zip_file}")
        return 1
    
    print("基盤地図情報の建物データをGeoJSONに変換中...")
    
    converter = XMLToGeoJSONConverter()
    features = converter.extract_and_convert_building_files(args.zip_file)
    
    if not features:
        print("建物データが見つかりませんでした。")
        return 1
    
    # GeoJSONファイルを作成
    geojson_data = {
        "type": "FeatureCollection",
        "features": features
    }
    
    # ファイルに出力
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(geojson_data, f, ensure_ascii=False, indent=2)
    
    print(f"変換完了!")
    print(f"出力ファイル: {args.output}")
    print(f"建物数: {len(features)}")
    
    return 0


if __name__ == '__main__':
    exit(main())

