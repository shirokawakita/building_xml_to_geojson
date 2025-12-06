#!/usr/bin/env python3
"""
基盤地図情報 XML to GeoJSON 変換 Streamlitアプリ

複数の基盤地図情報ZIPファイルをアップロードして、
建物ポリゴンをGeoJSONに変換し、結合して出力します。
"""

import streamlit as st
import zipfile
import json
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
import io
from pathlib import Path


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
    
    def parse_building_xml(self, xml_content: str, source_zip_name: str = None) -> List[Dict[str, Any]]:
        """建物XMLファイルをパースしてGeoJSONフィーチャーのリストを返す"""
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            st.error(f"XMLパースエラー: {e}")
            return []
        
        features = []
        
        # 建物要素を検索（名前空間付きで検索）
        building_elements = root.findall(f'.//{self.fgd_ns}BldA')
        
        # 各建物要素を処理
        for building in building_elements:
            # 座標を取得
            poslist = building.find(f'.//{self.gml_ns}posList')
            if poslist is not None and poslist.text:
                coords = self.parse_coordinates(poslist.text)
                
                if len(coords) >= 3:  # ポリゴンの場合、最低3点必要
                    # 属性情報を取得
                    properties = {}
                    
                    # 元のZIPファイル名を先頭に追加
                    if source_zip_name:
                        properties['source_file'] = source_zip_name
                    
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
    
    def extract_and_convert_building_files(self, zip_data: bytes, zip_name: str) -> List[Dict[str, Any]]:
        """ZIPファイルから建物ファイルを抽出してGeoJSONに変換
        
        メインZIPファイル（中にサブZIPファイルが入っている）と
        サブZIPファイル（直接XMLファイルが入っている）の両方に対応
        """
        all_features = []
        
        try:
            with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as main_zip:
                # メインZIP内のファイル一覧を取得
                file_list = main_zip.namelist()
                zip_files = [f for f in file_list if f.endswith('.zip')]
                xml_files = [f for f in file_list if '-BldA-' in f and f.endswith('.xml')]
                
                # ケース1: メインZIPファイル（中にサブZIPファイルが入っている）
                if zip_files:
                    for sub_zip_name in zip_files:
                        try:
                            # サブZIPファイルを読み込み
                            with main_zip.open(sub_zip_name) as sub_zip_data:
                                with zipfile.ZipFile(sub_zip_data, 'r') as sub_zip:
                                    # サブZIP内のファイル一覧を取得
                                    sub_file_list = sub_zip.namelist()
                                    
                                    # -BldA-を含むファイルを検索
                                    building_files = [f for f in sub_file_list if '-BldA-' in f and f.endswith('.xml')]
                                    
                                    for building_file in building_files:
                                        try:
                                            # XMLファイルを読み込み
                                            with sub_zip.open(building_file) as xml_data:
                                                xml_content = xml_data.read().decode('utf-8')
                                            
                                            # XMLをGeoJSONに変換（元のZIPファイル名を渡す）
                                            features = self.parse_building_xml(xml_content, source_zip_name=zip_name)
                                            all_features.extend(features)
                                            
                                        except Exception as e:
                                            st.warning(f"エラー ({sub_zip_name}/{building_file}): {e}")
                                            continue
                        except Exception as e:
                            st.warning(f"サブZIPファイルの処理エラー ({sub_zip_name}): {e}")
                            continue
                
                # ケース2: サブZIPファイル（直接XMLファイルが入っている）
                elif xml_files:
                    for building_file in xml_files:
                        try:
                            # XMLファイルを直接読み込み
                            with main_zip.open(building_file) as xml_data:
                                xml_content = xml_data.read().decode('utf-8')
                            
                            # XMLをGeoJSONに変換（元のZIPファイル名を渡す）
                            features = self.parse_building_xml(xml_content, source_zip_name=zip_name)
                            all_features.extend(features)
                            
                        except Exception as e:
                            st.warning(f"エラー ({building_file}): {e}")
                            continue
                
                else:
                    st.warning(f"ZIPファイル内に建物データ（-BldA-）が見つかりませんでした: {zip_name}")
                    
        except Exception as e:
            st.error(f"ZIPファイルの処理エラー ({zip_name}): {e}")
        
        return all_features


def main():
    st.set_page_config(
        page_title="基盤地図情報 XML to GeoJSON 変換",
        page_icon="🗾",
        layout="wide"
    )
    
    st.title("🗾 基盤地図情報 XML to GeoJSON 変換ツール")
    st.markdown("---")
    
    st.markdown("""
    ### 使い方
    1. 複数の基盤地図情報ZIPファイルをアップロードしてください
    2. 「変換開始」ボタンをクリックしてください
    3. 変換が完了したら、結合されたGeoJSONファイルをダウンロードできます
    """)
    
    # ファイルアップローダー
    uploaded_files = st.file_uploader(
        "基盤地図情報ZIPファイルを選択してください（複数選択可能）",
        type=['zip'],
        accept_multiple_files=True
    )
    
    if uploaded_files:
        st.info(f"{len(uploaded_files)}個のZIPファイルがアップロードされました")
        
        # 変換ボタン
        if st.button("🔄 変換開始", type="primary", use_container_width=True):
            converter = FastXMLToGeoJSONConverter()
            all_features = []
            total_files = len(uploaded_files)
            
            # プログレスバー
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for idx, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"処理中: {uploaded_file.name} ({idx + 1}/{total_files})")
                
                # ZIPファイルを読み込み
                zip_data = uploaded_file.read()
                
                # 変換処理
                features = converter.extract_and_convert_building_files(zip_data, uploaded_file.name)
                all_features.extend(features)
                
                # プログレスバーを更新
                progress_bar.progress((idx + 1) / total_files)
            
            status_text.text("変換完了！")
            progress_bar.empty()
            
            if all_features:
                # GeoJSONファイルを作成
                geojson_data = {
                    "type": "FeatureCollection",
                    "features": all_features
                }
                
                # 結果を表示
                st.success(f"✅ 変換完了！合計 {len(all_features)} 個の建物ポリゴンが変換されました")
                
                # 統計情報
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("処理したZIPファイル数", total_files)
                with col2:
                    st.metric("変換された建物数", len(all_features))
                with col3:
                    st.metric("出力ファイルサイズ", f"{len(json.dumps(geojson_data)) / 1024 / 1024:.2f} MB")
                
                # GeoJSONをJSON文字列に変換
                geojson_json = json.dumps(geojson_data, ensure_ascii=False, indent=2)
                
                # 出力ファイル名を生成（入力ZIPファイル名を先頭に含める）
                if total_files == 1:
                    # 1つのファイルの場合
                    base_name = Path(uploaded_files[0].name).stem  # 拡張子を除いたファイル名
                    output_filename = f"{base_name}_buildings.geojson"
                else:
                    # 複数のファイルの場合
                    base_name = Path(uploaded_files[0].name).stem  # 最初のファイル名を使用
                    output_filename = f"{base_name}_merged_buildings.geojson"
                
                # ダウンロードボタン
                st.download_button(
                    label="📥 GeoJSONファイルをダウンロード",
                    data=geojson_json,
                    file_name=output_filename,
                    mime="application/geo+json",
                    use_container_width=True
                )
                
                # プレビュー表示（最初の10件のみ）
                with st.expander("📋 変換結果のプレビュー（最初の10件）"):
                    preview_features = all_features[:10]
                    preview_geojson = {
                        "type": "FeatureCollection",
                        "features": preview_features
                    }
                    st.json(preview_geojson)
                
            else:
                st.warning("⚠️ 建物データが見つかりませんでした。ZIPファイルの内容を確認してください。")
    
    else:
        st.info("👆 上記から基盤地図情報のZIPファイルをアップロードしてください")
    
    # フッター
    st.markdown("---")
    st.markdown("""
    ### 注意事項
    - 基盤地図情報のXMLファイルはGML形式で記述されています
    - 座標系は日本測地系2000（JGD2000）または世界測地系（WGS84）です
    - 大きなファイルを処理する場合は、処理に時間がかかる場合があります
    - 複数のZIPファイルをアップロードした場合、すべての建物データが一つのGeoJSONファイルに結合されます
    """)


if __name__ == '__main__':
    main()
