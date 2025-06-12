import requests
import json
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

class EmergencyServiceHandler:
    def __init__(self):
        self.service_key = os.getenv('EMERGENCY_KEY')
        self.base_url = 'http://apis.data.go.kr/1352000/ODMS_EMG_02/callEmg02Api'
    
    def search_emergency_service(self, sido, sigungu):
        """
        응급안전안심 서비스 API 호출
        
        Args:
            sido: 시도명 (예: '서울특별시', '경기도')
            sigungu: 시군구명 (예: '성북구', '수원시')
        """
        print(f"[DEBUG] search_emergency_service 시작 - sido: {sido}, sigungu: {sigungu}")
        
        if not self.service_key:
            print("[DEBUG] EMERGENCY_KEY가 없음")
            return {
                "status": "error",
                "error": "EMERGENCY_KEY가 설정되지 않았습니다.",
                "source": "emergency_service"
            }
        
        if not sido or not sigungu:
            print("[DEBUG] 위치 정보 누락")
            return {
                "status": "error",
                "error": "위치 정보가 필요합니다.",
                "source": "emergency_service"
            }
        
        # API 파라미터 설정
        params = {
            'serviceKey': self.service_key,
            'numOfRows': '10',
            'pageNo': '1',
            'apiType': 'JSON',
            'sido': sido,
            'sigungu': sigungu
        }
        
        print(f"[DEBUG] API 파라미터: {params}")
        
        try:
            print(f"응급안전안심 서비스 API 호출 - 시도: {sido}, 시군구: {sigungu}")
            
            # API 호출
            response = requests.get(self.base_url, params=params)
            response.encoding = 'utf-8'
            
            print(f"[DEBUG] API 응답 상태 코드: {response.status_code}")
            
            if response.status_code == 200:
                print("[DEBUG] 200 OK 응답 받음")
                
                try:
                    data = response.json()
                    print(f"[DEBUG] JSON 파싱 성공")
                except json.JSONDecodeError as e:
                    print(f"[DEBUG] JSON 파싱 실패: {e}")
                    print(f"[DEBUG] 응답 텍스트: {response.text[:500]}")
                    return {
                        "status": "error",
                        "source": "emergency_service",
                        "error": f"JSON 파싱 오류: {str(e)}"
                    }
                
                # API 응답이 두 가지 형식 중 하나일 수 있음
                # 1. response로 감싸진 경우
                # 2. 직접 최상위에 있는 경우
                
                if 'response' in data:
                    # 형식 1: response로 감싸진 경우
                    response_data = data['response']
                    result_code = response_data.get('header', {}).get('resultCode')
                    result_msg = response_data.get('header', {}).get('resultMsg')
                    body = response_data.get('body', {})
                    items = body.get('items', {})
                    total_count = body.get('totalCount', 0)
                else:
                    # 형식 2: 직접 최상위에 있는 경우
                    print("[DEBUG] 직접 응답 형식 감지")
                    result_code = data.get('resultCode')
                    result_msg = data.get('resultMsg')
                    items = data.get('items', {})
                    total_count = data.get('totalCount', 0)
                
                print(f"[DEBUG] API 결과 코드: {result_code}")
                print(f"[DEBUG] API 결과 메시지: {result_msg}")
                print(f"[DEBUG] 전체 개수: {total_count}")
                print(f"[DEBUG] items 타입: {type(items)}")
                print(f"[DEBUG] items 내용: {items}")
                
                if result_code == '00':  # 성공
                    # items가 dict인지 list인지 확인
                    item_list = None
                    
                    if isinstance(items, list):
                        # items가 직접 리스트인 경우
                        item_list = items
                        print(f"[DEBUG] items가 직접 리스트입니다. 길이: {len(item_list)}")
                    elif isinstance(items, dict) and 'item' in items:
                        # items가 dict이고 'item' 키가 있는 경우
                        item_list = items['item']
                        if isinstance(item_list, dict):
                            item_list = [item_list]
                        print(f"[DEBUG] items['item']에서 데이터 추출. 길이: {len(item_list)}")
                    
                    if item_list and len(item_list) > 0:
                        print(f"[DEBUG] {len(item_list)}개의 결과 발견")
                        
                        # 결과 포맷팅
                        formatted_results = []
                        for idx, item in enumerate(item_list):
                            print(f"[DEBUG] 항목 {idx}: {item.get('organNm', 'N/A')}")
                            formatted_item = {
                                "organNm": item.get('organNm', '정보 없음'),
                                "organAddr": item.get('organAddr', '정보 없음'),
                                "organTel": item.get('organTel', '정보 없음'),
                                "organEmail": item.get('organEmail', '정보 없음'),
                                "bzType": item.get('bzType', '정보 없음'),
                                "organType": item.get('organType', '정보 없음')
                            }
                            formatted_results.append(formatted_item)
                        
                        return {
                            "status": "success",
                            "source": "emergency_service",
                            "location": {
                                "sido": sido,
                                "sigungu": sigungu
                            },
                            "total_count": total_count,
                            "results": formatted_results
                        }
                    else:
                        print("[DEBUG] 검색 결과 없음")
                        return {
                            "status": "success",
                            "source": "emergency_service",
                            "location": {
                                "sido": sido,
                                "sigungu": sigungu
                            },
                            "total_count": 0,
                            "results": [],
                            "message": f"{sido} {sigungu} 지역에 등록된 응급안전안심서비스 기관이 없습니다."
                        }
                else:
                    print(f"[DEBUG] API 오류 코드: {result_code}")
                    return {
                        "status": "error",
                        "source": "emergency_service",
                        "error": f"API 오류: {result_msg or '알 수 없는 오류'}"
                    }
            else:
                print(f"[DEBUG] HTTP 오류: {response.status_code}")
                return {
                    "status": "error",
                    "source": "emergency_service",
                    "error": f"API 호출 실패: 상태 코드 {response.status_code}"
                }
                
        except requests.exceptions.RequestException as e:
            print(f"[DEBUG] 요청 예외: {type(e).__name__}: {str(e)}")
            return {
                "status": "error",
                "source": "emergency_service",
                "error": f"네트워크 오류: {str(e)}"
            }
        except Exception as e:
            print(f"[DEBUG] 예상치 못한 예외: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "source": "emergency_service",
                "error": f"API 호출 중 오류 발생: {str(e)}"
            }
        
        # 이 부분에 도달하면 안됨
        print("[DEBUG] WARNING: 함수 끝에 도달 - 이것은 버그입니다!")
        return {
            "status": "error",
            "source": "emergency_service",
            "error": "알 수 없는 오류 - 함수가 예상치 못한 경로로 종료됨"
        }