import requests
import json
import os
import pandas as pd
from urllib.parse import unquote
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from datetime import datetime

# .env 파일 로드
load_dotenv()

class ExercisePrescriptionVideoFetcher:
    def __init__(self, service_key):
        self.service_key = service_key
        self.base_url = "http://apis.data.go.kr/B551014/SRVC_TODZ_VDO_PKG"
        self.endpoint = "TODZ_VDO_TRNG_VIDEO_I"
        
    def _parse_xml_response(self, xml_text):
        """XML 응답을 파싱하여 딕셔너리로 변환"""
        try:
            root = ET.fromstring(xml_text)
            
            def xml_to_dict(element):
                result = {}
                if element.attrib:
                    result['@attributes'] = element.attrib
                
                children = list(element)
                if children:
                    child_dict = {}
                    for child in children:
                        child_data = xml_to_dict(child)
                        if child.tag in child_dict:
                            if not isinstance(child_dict[child.tag], list):
                                child_dict[child.tag] = [child_dict[child.tag]]
                            child_dict[child.tag].append(child_data)
                        else:
                            child_dict[child.tag] = child_data
                    result.update(child_dict)
                
                if element.text and element.text.strip():
                    if result:
                        result['#text'] = element.text.strip()
                    else:
                        return element.text.strip()
                
                return result if result else None
            
            return {root.tag: xml_to_dict(root)}
        except ET.ParseError as e:
            print(f"XML 파싱 오류: {e}")
            return None
    
    def _make_request(self, params=None):
        """API 요청"""
        if params is None:
            params = {}
        
        # 필수 파라미터
        params['serviceKey'] = unquote(self.service_key)
        params['resultType'] = params.get('resultType', 'xml')
        
        # 기본 페이징 파라미터
        params['pageNo'] = params.get('pageNo', 1)
        params['numOfRows'] = params.get('numOfRows', 100)
        
        url = f"{self.base_url}/{self.endpoint}"
        
        print(f"\n요청 URL: {url}")
        print(f"파라미터: {params}")
        
        try:
            response = requests.get(url, params=params)
            response.encoding = 'utf-8'
            
            if response.status_code != 200:
                print(f"HTTP 오류: {response.status_code}")
                return None
            
            content = response.text.strip()
            
            if content.startswith('<?xml') or content.startswith('<'):
                parsed_xml = self._parse_xml_response(content)
                if parsed_xml:
                    if 'response' in parsed_xml:
                        return parsed_xml
                    else:
                        return {'response': parsed_xml}
            
            return None
        except Exception as e:
            print(f"요청 오류: {e}")
            return None
    
    def get_videos_by_filter(self, aggrp_nm=None, trng_plc_nm=None, trng_nm=None, tool_nm=None, max_videos=None):
        """필터 조건에 따른 운동처방동영상 조회"""
        
        # 필터 이름 생성
        filter_desc = []
        if aggrp_nm: filter_desc.append(f"연령대:{aggrp_nm}")
        if trng_plc_nm: filter_desc.append(f"장소:{trng_plc_nm}")
        if trng_nm: filter_desc.append(f"운동:{trng_nm}")
        if tool_nm: filter_desc.append(f"도구:{tool_nm}")
        
        filter_text = " / ".join(filter_desc) if filter_desc else "전체"
        print(f"\n=== 운동처방동영상 조회 ({filter_text}) ===")
        
        unique_videos = {}
        page_no = 1
        total_frames = 0
        
        while True:
            # 요청 파라미터 구성
            params = {
                'pageNo': page_no,
                'numOfRows': 100
            }
            
            # 필터 파라미터 추가
            if aggrp_nm:
                params['aggrp_nm'] = aggrp_nm
            if trng_plc_nm:
                params['trng_plc_nm'] = trng_plc_nm
            if trng_nm:
                params['trng_nm'] = trng_nm
            if tool_nm:
                params['tool_nm'] = tool_nm
            
            # API 요청
            result = self._make_request(params)
            
            if not result:
                break
            
            try:
                response = result.get('response', {})
                header = response.get('header', {})
                
                # 오류 확인
                result_code = header.get('resultCode', '')
                if result_code != '00':
                    print(f"API 오류: {header.get('resultMsg', '')}")
                    break
                
                # 데이터 추출
                body = response.get('body', {})
                items = body.get('items', {})
                item_list = items.get('item', [])
                
                if isinstance(item_list, dict):
                    item_list = [item_list]
                
                if not item_list:
                    print("더 이상 데이터가 없습니다.")
                    break
                
                # 각 항목 처리
                for item in item_list:
                    file_url = item.get('file_url', '')
                    if file_url and file_url not in unique_videos:
                        unique_videos[file_url] = {
                            'file_url': file_url,
                            'vdo_ttl_nm': item.get('vdo_ttl_nm', ''),
                            'trng_nm': item.get('trng_nm', ''),
                            'file_nm': item.get('file_nm', ''),
                            'vdo_desc': item.get('vdo_desc', ''),
                            'vdo_len': item.get('vdo_len', 0),
                            'file_sz': item.get('file_sz', 0),
                            'aggrp_nm': item.get('aggrp_nm', ''),
                            'trng_plc_nm': item.get('trng_plc_nm', ''),
                            'tool_nm': item.get('tool_nm', ''),
                            'fbctn_yr': item.get('fbctn_yr', ''),
                            'oper_nm': item.get('oper_nm', ''),
                            'lang': item.get('lang', '')
                        }
                
                total_frames += len(item_list)
                
                # 페이징 확인
                total_count = int(body.get('totalCount', 0))
                print(f"  페이지 {page_no}: {len(item_list)}개 항목 처리 (전체: {total_count})")
                
                if page_no * 100 >= total_count:
                    break
                
                # 최대 동영상 수 제한
                if max_videos and len(unique_videos) >= max_videos:
                    break
                
                page_no += 1
                
            except Exception as e:
                print(f"데이터 처리 오류: {e}")
                import traceback
                traceback.print_exc()
                break
        
        print(f"  - 총 {total_frames}개 프레임에서 {len(unique_videos)}개 고유 동영상 발견")
        return unique_videos
    
    def get_all_age_groups(self):
        """모든 연령대 목록 조회"""
        print("\n연령대별 동영상 수를 확인하는 중...")
        
        # 첫 페이지만 조회하여 연령대 목록 추출
        result = self._make_request({'pageNo': 1, 'numOfRows': 100})
        
        age_groups = set()
        if result:
            try:
                response = result.get('response', {})
                body = response.get('body', {})
                items = body.get('items', {})
                item_list = items.get('item', [])
                
                if isinstance(item_list, dict):
                    item_list = [item_list]
                
                for item in item_list:
                    age_group = item.get('aggrp_nm', '')
                    if age_group:
                        age_groups.add(age_group)
            except:
                pass
        
        return sorted(list(age_groups))
    
    def get_all_places(self):
        """모든 운동장소 목록 조회"""
        print("\n운동장소별 동영상 수를 확인하는 중...")
        
        # 첫 페이지만 조회하여 장소 목록 추출
        result = self._make_request({'pageNo': 1, 'numOfRows': 100})
        
        places = set()
        if result:
            try:
                response = result.get('response', {})
                body = response.get('body', {})
                items = body.get('items', {})
                item_list = items.get('item', [])
                
                if isinstance(item_list, dict):
                    item_list = [item_list]
                
                for item in item_list:
                    place = item.get('trng_plc_nm', '')
                    if place:
                        places.add(place)
            except:
                pass
        
        return sorted(list(places))


# 메인 실행
if __name__ == "__main__":
    # Windows 콘솔 인코딩 설정
    import sys
    if sys.platform == 'win32':
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    
    # 서비스 키 로드
    SERVICE_KEY = os.getenv("EXERCISE_KEY")
    if not SERVICE_KEY:
        print("환경변수 EXERCISE_KEY가 설정되지 않았습니다.")
        exit(1)
    
    # 페처 생성
    fetcher = ExercisePrescriptionVideoFetcher(SERVICE_KEY)
    
    # 1. 전체 운동처방동영상 조회
    print("=== 운동처방동영상 조회 시작 ===")
    all_videos = fetcher.get_videos_by_filter(max_videos=200)
    
    # 2. 특정 조건으로 조회 예시
    # 예시 1: 특정 연령대
    # videos_60s = fetcher.get_videos_by_filter(aggrp_nm="60대", max_videos=50)
    
    # 예시 2: 특정 운동장소
    # videos_home = fetcher.get_videos_by_filter(trng_plc_nm="집", max_videos=50)
    
    # 예시 3: 특정 운동명
    # videos_stretch = fetcher.get_videos_by_filter(trng_nm="스트레칭", max_videos=50)
    
    # 예시 4: 복합 조건
    # videos_complex = fetcher.get_videos_by_filter(
    #     aggrp_nm="50대",
    #     trng_plc_nm="집",
    #     max_videos=50
    # )
    
    # DataFrame으로 변환
    if all_videos:
        df = pd.DataFrame.from_dict(all_videos, orient='index')
        
        # 결과 출력
        print(f"\n=== 조회 완료 ===")
        print(f"총 {len(df)}개의 고유 운동처방동영상을 찾았습니다.")
        
        # 통계 출력
        if not df.empty:
            print("\n연령대별 동영상 수:")
            print(df['aggrp_nm'].value_counts())
            
            print("\n운동장소별 동영상 수:")
            print(df['trng_plc_nm'].value_counts())
            
            print("\n운동명별 동영상 수 (상위 10개):")
            print(df['trng_nm'].value_counts().head(10))
            
            # 샘플 출력
            print("\n처음 5개 동영상:")
            display_cols = ['vdo_ttl_nm', 'trng_nm', 'aggrp_nm', 'trng_plc_nm', 'vdo_len']
            print(df[display_cols].head())
            
            # CSV로 저장
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f'exercise_prescription_videos_{timestamp}.csv'
            df.to_csv(filename, index=False, encoding='utf-8-sig')
            print(f"\n동영상 정보를 '{filename}' 파일로 저장했습니다.")
            
            # URL 목록만 텍스트 파일로 저장
            url_filename = f'prescription_video_urls_{timestamp}.txt'
            with open(url_filename, 'w', encoding='utf-8') as f:
                for url in df['file_url']:
                    f.write(url + '\n')
            print(f"URL만 추출한 파일을 '{url_filename}'로 저장했습니다.")
            
            # 상세 정보 출력 (선택사항)
            print("\n상세 정보를 보시겠습니까? (y/n): ", end='')
            if input().lower() == 'y':
                for idx, row in df.head(10).iterrows():
                    print(f"\n--- 동영상 {idx+1} ---")
                    print(f"제목: {row['vdo_ttl_nm']}")
                    print(f"운동명: {row['trng_nm']}")
                    print(f"연령대: {row['aggrp_nm']}")
                    print(f"운동장소: {row['trng_plc_nm']}")
                    print(f"도구: {row.get('tool_nm', '없음')}")
                    print(f"영상 길이: {row['vdo_len']}초")
                    print(f"파일 크기: {row['file_sz']:,} bytes")
                    print(f"URL: {row['file_url']}")
    else:
        print("\n조회된 동영상이 없습니다.")