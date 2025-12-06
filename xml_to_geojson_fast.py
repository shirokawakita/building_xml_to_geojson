#!/usr/bin/env python3
"""
基盤地図情報の建物データ（-BldA-）をXMLからGeoJSONに変換するスクリプト（高速版）

使用方法:
    python xml_to_geojson_fast.py <zip_file_path>

例:
    python xml_to_geojson_fast.py 20250918090652709-001.zip
"""

import argparse
import json
import os
import zipfile
from pathlib import Path
from typing import List, Dict, Any
import xml.etree.ElementTree as ET


class FastXMLToGeoJSONConverter:
    """基盤地図情報のXMLを高速でGeoJSONに変換するクラス"""
    
    def __init__(self):
        self.fgd_ns = '{http://fgd.gsi.go.jp/spec/2008/FGD_GMLSchema}'
        self.gml_ns = '{http://www.opengis.net/gml/3.2}'
    
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
    
    def parse_building_xml(self, xml_content: str) -> List[Dict[str, Any]]:
        """建物XMLファイルをパースしてGeoJSONフィーチャーのリストを返す"""
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            print(f"XMLパースエラー: {e}")
            return []
        
        features = []
        
        # 建物要素を検索（名前空間付きで検索）
        building_elements = root.findall(f'.//{self.fgd_ns}BldA')
        
        print(f"  見つかった建物要素数: {len(building_elements)}")
        
        # 各建物要素を処理
        for i, building in enumerate(building_elements):
            if i % 1000 == 0 and i > 0:
                print(f"    処理中: {i}/{len(building_elements)}")
            
            # 座標を取得
            poslist = building.find(f'.//{self.gml_ns}posList')
            if poslist is not None and poslist.text:
                coords = self.parse_coordinates(poslist.text)
                
                if len(coords) >= 3:  # ポリゴンの場合、最低3点必要
                    # 属性情報を取得
                    properties = {}
                    
                    # 属性情報を取得
                    for child in building:
                        if child.tag.startswith('{') and child.tag.endswith('}'):
                            tag_name = child.tag.split('}')[1]
                        else:
                            tag_name = child.tag
                        
                        if tag_name in ['fid', 'type', 'orgGILvl']:
                            properties[tag_name] = child.text
                    
                    # gml:id属性も取得
                    if 'gml:id' in building.attrib:
                        properties['gml_id'] = building.attrib['gml:id']
                    
                    # フィーチャーを作成
                    feature = {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [coords]
                        },
                        "properties": properties
                    }
                    
                    features.append(feature)
        
        return features
    
    def extract_and_convert_building_files(self, zip_path: str, max_files: int = None) -> List[Dict[str, Any]]:
        """ZIPファイルから建物ファイルを抽出してGeoJSONに変換"""
        all_features = []
        
        with zipfile.ZipFile(zip_path, 'r') as main_zip:
            print(f"メインZIPファイルを処理中: {zip_path}")
            
            # メインZIP内のファイル一覧を取得
            file_list = main_zip.namelist()
            zip_files = [f for f in file_list if f.endswith('.zip')]
            
            if max_files:
                zip_files = zip_files[:max_files]
            
            print(f"処理するサブZIPファイル数: {len(zip_files)}")
            
            for i, sub_zip_name in enumerate(zip_files):
                print(f"処理中 ({i+1}/{len(zip_files)}): {sub_zip_name}")
                
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
    parser = argparse.ArgumentParser(description='基盤地図情報の建物データをXMLからGeoJSONに変換（高速版）')
    parser.add_argument('zip_file', help='基盤地図情報のZIPファイルパス')
    parser.add_argument('-o', '--output', default='buildings.geojson', help='出力ファイル名（デフォルト: buildings.geojson）')
    parser.add_argument('--max-files', type=int, help='処理するサブZIPファイルの最大数（テスト用）')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.zip_file):
        print(f"エラー: ファイルが見つかりません: {args.zip_file}")
        return 1
    
    print("基盤地図情報の建物データをGeoJSONに変換中（高速版）...")
    
    converter = FastXMLToGeoJSONConverter()
    features = converter.extract_and_convert_building_files(args.zip_file, args.max_files)
    
    if not features:
        print("建物データが見つかりませんでした。")
        return 1
    
    # GeoJSONファイルを作成
    geojson_data = {
        "type": "FeatureCollection",
        "features": features
    }
    
    # ファイルに出力
    print(f"GeoJSONファイルに出力中: {args.output}")
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(geojson_data, f, ensure_ascii=False, indent=2)
    
    print(f"変換完了!")
    print(f"出力ファイル: {args.output}")
    print(f"建物数: {len(features)}")
    
    return 0


if __name__ == '__main__':
    exit(main())






