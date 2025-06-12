import os
import sys
import json
import requests
from dotenv import load_dotenv

# Windows 콘솔 UTF-8 설정
if sys.platform == 'win32':
    import subprocess
    subprocess.run(['chcp', '65001'], shell=True, capture_output=True)

# Load .env file
load_dotenv()

# 환경변수에서 서비스 키 가져오기
SERVICE_KEY = os.getenv('EMERGENCY_KEY')

# API URL 구성
base_url = 'http://apis.data.go.kr/1352000/ODMS_EMG_02/callEmg02Api'
params = {
    'serviceKey': SERVICE_KEY,
    'numOfRows': '10',
    'pageNo': '1',
    'apiType': 'JSON',  # JSON 형식으로 변경
    'sido': '서울특별시',
    'sigungu': '강북구'
}

def print_info(item):
    """필요한 정보만 출력하는 함수"""
    fields = {
        'sido': '시도',
        'sigungu': '시군구',
        'organNm': '기관명',
        'organAddr': '주소',
        'bzType': '사업유형',
        'organType': '기관유형',
        'organTel': '전화번호',
        'organEmail' : '이메일'
    }
    
    for key, label in fields.items():
        value = item.get(key, 'N/A')
        if value and value != 'null':
            print(f"{label}: {value}")
        else:
            print(f"{label}: 정보 없음")

try:
    # API 호출
    print("API 호출 중...")
    response = requests.get(base_url, params=params)
    response.encoding = 'utf-8'
    
    # 응답 상태 확인
    if response.status_code == 200:
        print("API 호출 성공!")
        print("=" * 60)
        
        try:
            # JSON 파싱
            data = response.json()
            
            # 응답 구조 확인
            if 'response' in data:
                response_data = data['response']
                
                # 헤더 정보 확인
                header = response_data.get('header', {})
                result_code = header.get('resultCode')
                result_msg = header.get('resultMsg')
                
                print(f"결과 코드: {result_code}")
                print(f"결과 메시지: {result_msg}")
                print("-" * 60)
                
                # 바디 정보 확인
                body = response_data.get('body', {})
                items = body.get('items', {})
                
                if items and 'item' in items:
                    item_list = items['item']
                    
                    # item이 단일 객체인 경우 리스트로 변환
                    if isinstance(item_list, dict):
                        item_list = [item_list]
                    
                    total_count = body.get('totalCount', 0)
                    print(f"전체 데이터 수: {total_count}")
                    print(f"현재 페이지 데이터 수: {len(item_list)}")
                    print("=" * 60)
                    
                    for idx, item in enumerate(item_list, 1):
                        print(f"\n[{idx}번째 데이터]")
                        print_info(item)
                        print("-" * 40)
                else:
                    print("조회된 데이터가 없습니다.")
            else:
                print("예상과 다른 응답 형식입니다.")
                print("응답 내용:", json.dumps(data, ensure_ascii=False, indent=2)[:500])
                
        except json.JSONDecodeError as e:
            print(f"JSON 파싱 오류: {e}")
            print("원본 응답:", response.text[:500])
            
    else:
        print(f"API 호출 실패. 상태 코드: {response.status_code}")
        print(f"응답 내용: {response.text[:500]}")
        
except requests.exceptions.RequestException as e:
    print(f"API 요청 중 오류 발생: {e}")
except Exception as e:
    print(f"예상치 못한 오류 발생: {e}")
    import traceback
    traceback.print_exc()

# 디버깅 정보
print("\n" + "=" * 60)
print("[디버깅 정보]")
print(f"사용된 URL: {base_url}")
print(f"파라미터: {params}")
print(f"서비스 키 존재 여부: {'있음' if SERVICE_KEY else '없음'}")

if not SERVICE_KEY:
    print("\n  주의: EXERCISE_KEY 환경변수가 설정되지 않았습니다.")
    print("   .env 파일에 EXERCISE_KEY=your_actual_key 형식으로 추가해주세요.")

# 결과를 파일로도 저장 (한글 확인용)
# try:
#     with open('api_result.txt', 'w', encoding='utf-8') as f:
#         f.write("API 호출 결과가 'api_result.txt' 파일에 저장되었습니다.\n")
#     print("\n결과가 'api_result.txt' 파일에도 저장되었습니다.")
# except:
#     pass