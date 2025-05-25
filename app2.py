from flask import Flask, request, jsonify
import os
import json
import traceback
import re
import sys
from threading import Thread
from dotenv import load_dotenv
import random

# UTF-8 인코딩 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# 환경 변수 설정 (한글 지원)
os.environ['PYTHONIOENCODING'] = 'utf-8'

# .env 파일에서 환경 변수 로드
load_dotenv()

app = Flask(__name__)

# Pinecone API 키
pinecone_api_key = os.getenv("PINECONE_API_KEY")
if not pinecone_api_key:
    print("경고: PINECONE_API_KEY가 설정되지 않았습니다.")
    pinecone_api_key = "dummy_key_for_testing"  # 테스트용 더미 키

# Gemini API 키
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    print("경고: GEMINI_API_KEY가 설정되지 않았습니다.")
    gemini_api_key = "dummy_key_for_testing"  # 테스트용 더미 키

# 인덱스 이름
dense_index_name = os.getenv("PINECONE_INDEX_NAME", "dense-for-hybrid-py")

# Pinecone 및 Gemini 모듈 초기화
try:
    from pinecone import Pinecone
    pc = Pinecone(api_key=pinecone_api_key)
    print("Pinecone 클라이언트 초기화 성공")
except ImportError:
    print("Pinecone 라이브러리를 찾을 수 없습니다. pip install pinecone-client로 설치하세요.")
    pc = None
except Exception as e:
    print(f"Pinecone 초기화 중 오류: {str(e)}")
    pc = None

try:
    from google import genai
    gemini_client = genai.Client(api_key=gemini_api_key)
    print("Gemini 클라이언트 초기화 성공")
except ImportError:
    print("Google Generative AI 라이브러리를 찾을 수 없습니다. pip install google-generative-ai로 설치하세요.")
    gemini_client = None
except Exception as e:
    print(f"Gemini 초기화 중 오류: {str(e)}")
    gemini_client = None

# Namespace 정보
NAMESPACE_INFO = {
    'seoul_job': '서울시 고용 정보, 채용 공고, 일자리 관련 데이터',
    'seoul_culture': '서울시 문화, 교육, 여가 프로그램 관련 데이터', 
    'seoul_facility': '서울시 장기요양기관, 방문요양센터, 복지관, 경로당, 노인교실 관련 데이터',
    'kk_job': '경기도 고용 정보, 채용 공고, 일자리 관련 데이터',
    'kk_culture': '경기도 문화, 교육, 여가 프로그램 관련 데이터', 
    'kk_facility': '경기도 장기요양기관, 방문요양센터, 복지관, 경로당, 노인교실 관련 데이터',
    'ich_job': '인천 고용 정보, 채용 공고, 일자리 관련 데이터',
    'ich_culture': '인천 문화, 교육, 여가 프로그램 관련 데이터',
    'ich_facility': '인천 장기요양기관, 방문요양센터, 복지관, 경로당, 노인교실 관련 데이터',
}

# 서울시 행정구역 간 인접 정보 (각 구와 인접한 구 목록)
SEOUL_DISTRICT_NEIGHBORS = {
    '강남구': ['서초구', '송파구', '강동구', '성동구', '용산구'],
    '강동구': ['송파구', '강남구', '광진구', '성동구'],
    '강북구': ['도봉구', '노원구', '성북구', '중랑구'],
    '강서구': ['양천구', '영등포구', '구로구', '마포구'],
    '관악구': ['동작구', '서초구', '금천구', '영등포구'],
    '광진구': ['성동구', '강동구', '송파구', '중랑구', '동대문구'],
    '구로구': ['양천구', '강서구', '영등포구', '금천구', '관악구'],
    '금천구': ['구로구', '영등포구', '관악구'],
    '노원구': ['도봉구', '강북구', '중랑구', '성북구'],
    '도봉구': ['강북구', '노원구', '성북구'],
    '동대문구': ['중랑구', '성북구', '성동구', '광진구', '종로구'],
    '동작구': ['영등포구', '관악구', '서초구', '용산구'],
    '마포구': ['서대문구', '용산구', '영등포구', '강서구', '양천구', '은평구'],
    '서대문구': ['은평구', '마포구', '용산구', '중구', '종로구'],
    '서초구': ['강남구', '용산구', '동작구', '관악구'],
    '성동구': ['광진구', '동대문구', '중구', '용산구', '강남구', '송파구', '강동구'],
    '성북구': ['강북구', '도봉구', '노원구', '중랑구', '동대문구', '종로구'],
    '송파구': ['강동구', '강남구', '성동구', '광진구'],
    '양천구': ['강서구', '영등포구', '구로구', '마포구'],
    '영등포구': ['양천구', '강서구', '마포구', '용산구', '동작구', '관악구', '구로구', '금천구'],
    '용산구': ['중구', '성동구', '강남구', '서초구', '동작구', '영등포구', '마포구', '서대문구', '종로구'],
    '은평구': ['서대문구', '마포구', '종로구'],
    '종로구': ['은평구', '서대문구', '중구', '성동구', '동대문구', '성북구'],
    '중구': ['종로구', '서대문구', '용산구', '성동구', '동대문구'],
    '중랑구': ['노원구', '광진구', '동대문구', '성북구', '강북구']
}


# 경기도 시·군 간 인접 정보 (각 시·군과 인접한 시·군 목록)
GYEONGGI_DISTRICT_NEIGHBORS = {
    # 북부 지역
    '연천군': ['포천시', '철원군', '파주시'],
    '포천시': ['연천군', '가평군', '남양주시', '의정부시', '동두천시', '철원군'],
    '가평군': ['포천시', '남양주시', '양평군', '춘천시'],
    '파주시': ['연천군', '고양시', '김포시', '개성시'],
    '동두천시': ['포천시', '양주시', '의정부시'],
    '양주시': ['동두천시', '의정부시', '구리시', '남양주시'],
    '의정부시': ['동두천시', '양주시', '구리시', '포천시'],
    
    # 서북부 지역  
    '고양시': ['파주시', '김포시', '부천시', '서울특별시'],
    '김포시': ['파주시', '고양시', '부천시', '인천광역시'],
    '부천시': ['고양시', '김포시', '광명시', '서울특별시', '인천광역시'],
    
    # 중부 지역
    '구리시': ['양주시', '의정부시', '남양주시', '하남시', '서울특별시'],
    '남양주시': ['포천시', '가평군', '양주시', '구리시', '하남시', '양평군'],
    '하남시': ['구리시', '남양주시', '광주시', '성남시', '서울특별시'],
    '양평군': ['가평군', '남양주시', '하남시', '광주시', '여주시', '원주시'],
    '광주시': ['하남시', '양평군', '여주시', '용인시', '성남시'],
    '여주시': ['양평군', '광주시', '이천시', '원주시', '충주시'],
    
    # 서부 지역
    '광명시': ['부천시', '시흥시', '안양시', '서울특별시'],
    '시흥시': ['광명시', '안양시', '군포시', '안산시', '인천광역시'],
    '안양시': ['광명시', '시흥시', '군포시', '의왕시', '과천시', '서울특별시'],
    '군포시': ['시흥시', '안양시', '의왕시', '안산시', '수원시'],
    '의왕시': ['안양시', '군포시', '수원시', '과천시', '성남시'],
    '과천시': ['안양시', '의왕시', '성남시', '서울특별시'],
    '안산시': ['시흥시', '군포시', '수원시', '화성시', '인천광역시'],
    
    # 중앙 지역
    '성남시': ['하남시', '광주시', '용인시', '의왕시', '과천시', '서울특별시'],
    '용인시': ['광주시', '성남시', '수원시', '화성시', '이천시', '안성시'],
    '수원시': ['군포시', '의왕시', '안산시', '화성시', '용인시', '오산시'],
    '화성시': ['안산시', '수원시', '용인시', '오산시', '평택시', '안성시'],
    '오산시': ['수원시', '화성시', '평택시'],
    
    # 남부 지역
    '평택시': ['화성시', '오산시', '안성시', '아산시', '천안시'],
    '안성시': ['용인시', '화성시', '평택시', '이천시', '천안시', '음성군'],
    '이천시': ['광주시', '여주시', '용인시', '안성시', '충주시', '음성군'],
}



# multi_query_category 정의 (파일 상단, NAMESPACE_INFO 아래에 추가)
MULTI_QUERY_CATEGORY = {
    '문화': '{user_city} {user_district}의 문화 정보',
    '정책': '{user_city} {user_district}의 정책 정보',
    '쇼핑': '{user_city} {user_district}의 쇼핑 정보, 쇼핑 특가',
    '일자리': '{user_city} {user_district}의 시니어 일자리 정보',
    '복지시설': '{user_city} {user_district}의 노인복지시설 정보',
    '건강': '{user_city} {user_district}의 시니어 건강 프로그램',
    '교육': '{user_city} {user_district}의 평생교육 프로그램',
    '여가': '{user_city} {user_district}의 시니어 여가 활동',
    '의료': '{user_city} {user_district}의 의료 서비스 안내',
    '교통': '{user_city} {user_district}의 시니어 교통 할인 정보',
    '주거': '{user_city} {user_district}의 시니어 주거 지원 정보',
    '식사': '{user_city} {user_district}의 경로식당 및 도시락 배달 서비스'
}


class QueryProcessor:
    def __init__(self, gemini_client, pinecone_client, dense_index_name="dense-for-hybrid-py"):
        """
        Initialize the QueryProcessor with API clients and index name.
        
        Args:
            gemini_client: Initialized Gemini client
            pinecone_client: Initialized Pinecone client
            dense_index_name: Name of the Pinecone index
        """
        self.gemini_client = gemini_client
        self.pc = pinecone_client
        self.dense_index_name = dense_index_name
        self.dense_index = None if self.pc is None else self.pc.Index(self.dense_index_name)
        
    def select_namespace(self, query, namespace_info=NAMESPACE_INFO):
        """
        Select the most appropriate namespace for a user query using Gemini.
        """
        if self.gemini_client is None:
            return {
                "namespace": None,
                "confidence": 0,
                "reasoning": "Gemini client is not initialized"
            }
            
        # Construct the prompt for the model
        prompt = f"""
당신은 사용자 질문에 가장 적합한 namespace를 선택하는 시스템입니다. 
다음 정보를 참고하여 주어진 질문이 어떤 namespace에 가장 적합한지 판단하세요.

### Namespace 정보:
{json.dumps(namespace_info, indent=2, ensure_ascii=False)}

### 사용자 질문:
{query}

### 응답 형식:
JSON 형식으로 응답해 주세요. 가장 적합한 namespace 하나와 그 선택에 대한 confidence score(0.0~1.0)를 제공하세요.
예시: {{"namespace": "namespace_key", "confidence": 0.95, "reasoning": "이 namespace를 선택한 이유"}}

항상 정확히 하나의 namespace만 선택하세요. 어떤 namespace에도 맞지 않는다면 confidence를 0.3 미만으로 설정하고 namespace를 null로 지정하세요.
"""

        # Generate response using Gemini
        try:
            response = self.gemini_client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            
            # Parse the JSON response
            try:
                # First, attempt to parse the response text directly
                result = json.loads(response.text)
                
                # Set namespace to None if confidence is very low (below 0.3)
                if result.get('confidence', 0) < 0.3:
                    result['namespace'] = None
                    
                return result
            except (json.JSONDecodeError, AttributeError):
                # If that fails, try to extract JSON from the text
                json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group(0))
                        
                        # Set namespace to None if confidence is very low
                        if result.get('confidence', 0) < 0.3:
                            result['namespace'] = None
                            
                        return result
                    except json.JSONDecodeError:
                        pass
                
                # Fallback
                return {
                    "namespace": None,
                    "confidence": 0,
                    "reasoning": "Failed to parse model response",
                    "raw_response": response.text
                }
        except Exception as e:
            return {
                "namespace": None,
                "confidence": 0,
                "reasoning": f"Error calling Gemini API: {str(e)}",
                "error": str(e)
            }
    
    def get_llm_response(self, query):
        """
        Get a direct response from Gemini when no namespace is appropriate.
        """
        if self.gemini_client is None:
            return {
                "source": "llm",
                "response": "Gemini client is not initialized",
                "status": "error"
            }
            
        try:
            # 날씨 관련 질문인지 확인
            weather_keywords = ["날씨", "기온", "강수", "비", "눈", "미세먼지", "황사", "자외선", "바람", "기상"]
            is_weather_query = any(keyword in query for keyword in weather_keywords)
            
            # 날씨 관련 질문이면 구체적인 답변 유도
            if is_weather_query:
                prompt = f"""
사용자가 날씨에 관한 다음 질문을 했습니다:
"{query}"

날씨 정보에 대해 가능한 한 구체적이고 유용한 답변을 제공해 주세요.
현재 서울의 날씨는 맑고, 기온은 24°C이며, 습도는 45%입니다. 
미세먼지는 '보통' 수준이고, 바람은 북서풍 3m/s로 불고 있습니다.
오늘의 최고 기온은 26°C, 최저 기온은 15°C로 예상됩니다.
내일은 흐리고 비가 올 수 있으며, 최고 기온 22°C, 최저 기온 14°C가 예상됩니다.

위 정보를 바탕으로 사용자 질문에 맞는 구체적인 답변을 제공해 주세요.
"""
            else:
                prompt = f"""
사용자 질문에 대해 직접 답변해주세요:
{query}
"""
            
            response = self.gemini_client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            return {
                "source": "llm",
                "response": response.text,
                "status": "success"
            }
        except Exception as e:
            return {
                "source": "llm",
                "response": f"오류가 발생했습니다: {str(e)}",
                "status": "error",
                "error": str(e)
            }
    
    def is_seoul_namespace(self, namespace):
        """
        네임스페이스가 서울 관련인지 확인합니다.
        """
        return namespace and namespace.startswith('seoul')
    
    def is_gyeonggi_namespace(self, namespace):
        """
        네임스페이스가 경기도 관련인지 확인합니다.
        """
        return namespace and namespace.startswith('kk')
    
    def extract_district_from_query(self, query, namespace):
        """
        사용자 쿼리에서 지역명을 추출합니다.
        네임스페이스에 따라 서울시 구 또는 경기도 시·군을 추출합니다.
        
        Args:
            query: 사용자 검색어
            namespace: 선택된 네임스페이스
            
        Returns:
            str: 추출된 지역명 (없으면 None)
        """
        if self.is_seoul_namespace(namespace):
            return self._extract_seoul_district(query)
        elif self.is_gyeonggi_namespace(namespace):
            return self._extract_gyeonggi_district(query)
        else:
            return None
    
    def _extract_seoul_district(self, query):
        """
        서울시 구 이름을 추출합니다.
        """
        all_districts = list(SEOUL_DISTRICT_NEIGHBORS.keys())
        
        # 정규식 패턴: '구' 글자가 포함된 단어
        pattern = r'(\w+구)'
        matches = re.findall(pattern, query)
        
        # 추출된 '구' 중에서 실제 서울시 구인지 확인
        for match in matches:
            if match in all_districts:
                return match
        
        # Gemini를 통한 구 추출 시도
        try:
            prompt = f"""
다음 사용자 질문에서 서울시 행정구역(구 이름)을 추출해주세요.
만약 특정 구 이름이 없다면 "없음"이라고 답해주세요.

### 사용자 질문:
{query}

### 가능한 서울시 구 목록:
{", ".join(all_districts)}

### 응답 형식:
구 이름만 답변해 주세요 (예: "강남구"). 없으면 "없음"이라고만 답변하세요.
"""
            response = self.gemini_client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            
            extracted_district = response.text.strip()
            if extracted_district in all_districts:
                return extracted_district
                
        except Exception as e:
            print(f"서울 구 추출 중 오류 발생: {str(e)}")
        
        return None
    
    def _extract_gyeonggi_district(self, query):
        """
        경기도 시·군 이름을 추출합니다.
        """
        all_districts = list(GYEONGGI_DISTRICT_NEIGHBORS.keys())
        
        # 정규식 패턴: '시' 또는 '군' 글자가 포함된 단어
        pattern = r'(\w+[시군])'
        matches = re.findall(pattern, query)
        
        # 추출된 시·군 중에서 실제 경기도 시·군인지 확인
        for match in matches:
            if match in all_districts:
                return match
        
        # Gemini를 통한 시·군 추출 시도
        try:
            prompt = f"""
다음 사용자 질문에서 경기도 행정구역(시 또는 군 이름)을 추출해주세요.
만약 특정 시·군 이름이 없다면 "없음"이라고 답해주세요.

### 사용자 질문:
{query}

### 가능한 경기도 시·군 목록:
{", ".join(all_districts)}

### 응답 형식:
시·군 이름만 답변해 주세요 (예: "수원시", "연천군"). 없으면 "없음"이라고만 답변하세요.
"""
            response = self.gemini_client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            
            extracted_district = response.text.strip()
            if extracted_district in all_districts:
                return extracted_district
                
        except Exception as e:
            print(f"경기도 시·군 추출 중 오류 발생: {str(e)}")
        
        return None
    
    def get_nearby_districts(self, district, namespace, max_neighbors=3):
        """
        지정된 지역과 인접한 지역 목록을 반환합니다.
        네임스페이스에 따라 서울 또는 경기도 인접 정보를 사용합니다.
        
        Args:
            district: 기준이 되는 지역 이름
            namespace: 선택된 네임스페이스
            max_neighbors: 최대 인접 지역 수
            
        Returns:
            list: 인접 지역 목록 (기준 지역 포함)
        """
        if self.is_seoul_namespace(namespace):
            return self._get_seoul_nearby_districts(district, max_neighbors)
        elif self.is_gyeonggi_namespace(namespace):
            return self._get_gyeonggi_nearby_districts(district, max_neighbors)
        else:
            return []
    
    def _get_seoul_nearby_districts(self, district, max_neighbors=3):
        """
        서울시 구의 인접 구 목록을 반환합니다.
        """
        if not district or district not in SEOUL_DISTRICT_NEIGHBORS:
            return ['강남구', '서초구', '종로구']  # 기본 인기 지역
        
        neighbors = SEOUL_DISTRICT_NEIGHBORS.get(district, [])[:max_neighbors]
        return [district] + neighbors
    
    def _get_gyeonggi_nearby_districts(self, district, max_neighbors=3):
        """
        경기도 시·군의 인접 시·군 목록을 반환합니다.
        """
        if not district or district not in GYEONGGI_DISTRICT_NEIGHBORS:
            return ['수원시', '성남시', '고양시']  # 기본 인기 지역
        
        neighbors = GYEONGGI_DISTRICT_NEIGHBORS.get(district, [])[:max_neighbors]
        return [district] + neighbors
    
    def select_relevant_nearby_districts(self, query, target_district, namespace, max_neighbors=3):
        """
        검색어와 관련성이 높은 인접 지역을 선택합니다.
        """
        if self.is_seoul_namespace(namespace):
            return self._select_seoul_relevant_districts(query, target_district, max_neighbors)
        elif self.is_gyeonggi_namespace(namespace):
            return self._select_gyeonggi_relevant_districts(query, target_district, max_neighbors)
        else:
            return self.get_nearby_districts(target_district, namespace, max_neighbors)
    
    def _select_seoul_relevant_districts(self, query, target_district, max_neighbors=3):
        """
        서울시 구 기준으로 관련성 높은 인접 구를 선택합니다.
        """
        if not target_district or target_district not in SEOUL_DISTRICT_NEIGHBORS:
            return self._get_seoul_nearby_districts(target_district, max_neighbors)
        
        try:
            prompt = f"""
사용자가 "{query}"라고 검색했고, 여기서 "{target_district}"를 검색 지역으로 식별했습니다.
다음 인접 구역 중에서 이 검색어와 가장 관련이 높을 것 같은 구역을 최대 {max_neighbors}개 선택해주세요:
{SEOUL_DISTRICT_NEIGHBORS[target_district]}

### 응답 형식:
JSON 형식으로 응답해 주세요. 선택한 구 이름만 배열로 제공하세요.
예시: ["구이름1", "구이름2", "구이름3"]
"""
            response = self.gemini_client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            
            try:
                neighbors = json.loads(response.text)
                if isinstance(neighbors, list) and all(isinstance(d, str) for d in neighbors):
                    valid_neighbors = [d for d in neighbors if d in SEOUL_DISTRICT_NEIGHBORS]
                    if valid_neighbors:
                        return [target_district] + valid_neighbors[:max_neighbors]
            except:
                pass
        except Exception as e:
            print(f"서울 인접 구 선택 중 오류 발생: {str(e)}")
        
        return self._get_seoul_nearby_districts(target_district, max_neighbors)
    
    def _select_gyeonggi_relevant_districts(self, query, target_district, max_neighbors=3):
        """
        경기도 시·군 기준으로 관련성 높은 인접 시·군을 선택합니다.
        """
        if not target_district or target_district not in GYEONGGI_DISTRICT_NEIGHBORS:
            return self._get_gyeonggi_nearby_districts(target_district, max_neighbors)
        
        try:
            prompt = f"""
사용자가 "{query}"라고 검색했고, 여기서 "{target_district}"를 검색 지역으로 식별했습니다.
다음 인접 시·군 중에서 이 검색어와 가장 관련이 높을 것 같은 시·군을 최대 {max_neighbors}개 선택해주세요:
{GYEONGGI_DISTRICT_NEIGHBORS[target_district]}

### 응답 형식:
JSON 형식으로 응답해 주세요. 선택한 시·군 이름만 배열로 제공하세요.
예시: ["시군이름1", "시군이름2", "시군이름3"]
"""
            response = self.gemini_client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            
            try:
                neighbors = json.loads(response.text)
                if isinstance(neighbors, list) and all(isinstance(d, str) for d in neighbors):
                    valid_neighbors = [d for d in neighbors if d in GYEONGGI_DISTRICT_NEIGHBORS]
                    if valid_neighbors:
                        return [target_district] + valid_neighbors[:max_neighbors]
            except:
                pass
        except Exception as e:
            print(f"경기도 인접 시·군 선택 중 오류 발생: {str(e)}")
        
        return self._get_gyeonggi_nearby_districts(target_district, max_neighbors)
    
    def search_pinecone(self, query, namespace, top_k=10, rerank_top_n=8):
        """
        Search Pinecone vector database using the specified namespace.
        """
        if self.dense_index is None:
            return {
                "source": "pinecone",
                "namespace": namespace,
                "results": None,
                "status": "error",
                "error": "Pinecone index is not initialized"
            }
            
        try:
            # UTF-8 인코딩으로 안전한 출력
            try:
                print(f"Searching Pinecone with namespace: {namespace}")
            except UnicodeEncodeError:
                print("Searching Pinecone with namespace: [encoding error]")
            
            # 검색어에서 지역명 추출 (네임스페이스에 따라 서울 구 또는 경기도 시·군)
            target_district = self.extract_district_from_query(query, namespace)
            
            try:
                print(f"추출된 지역: {target_district if target_district else 'None'}")
            except UnicodeEncodeError:
                print("추출된 지역: [encoding error]")
            
            # 대상 지역과 인접 지역 목록 가져오기 (관련성 기반 선택)
            districts_to_search = self.select_relevant_nearby_districts(query, target_district, namespace, max_neighbors=3)
            
            try:
                districts_str = ', '.join(districts_to_search) if districts_to_search else 'None'
                print(f"검색할 지역 목록: [{districts_str}]")
            except UnicodeEncodeError:
                print("검색할 지역 목록: [encoding error]")
            
            # 검색 필터 구성
            search_filter = None
            if districts_to_search:
                search_filter = {"Category": {"$in": districts_to_search}}
            
            # 검색 실행
            search_params = {
                "inputs": {"text": query},
                "top_k": top_k
            }
            
            # 필터가 있는 경우에만 추가
            if search_filter:
                search_params["filter"] = search_filter
            
            ranked_results = self.dense_index.search(
                namespace=namespace,
                query=search_params,
                fields=["Title", "Category", "chunk_text"],
                rerank={
                    "model": "bge-reranker-v2-m3",
                    "top_n": rerank_top_n,
                    "rank_fields": ["chunk_text"]
                },
            )
            
            # 검색 정보를 디버그 정보에 추가
            search_info = {
                "target_district": target_district,
                "districts_searched": districts_to_search,
                "region_type": "seoul" if self.is_seoul_namespace(namespace) else "gyeonggi" if self.is_gyeonggi_namespace(namespace) else "other"
            }
            
            # 상세한 검색 결과 출력
            if ranked_results and 'result' in ranked_results and 'hits' in ranked_results['result']:
                hits = ranked_results['result']['hits']
                result_count = len(hits)
                
                print(f"\n{'='*60}")
                print(f"🔍 검색 결과: 총 {result_count}개 항목")
                print(f"📍 검색어: {query}")
                print(f"📂 네임스페이스: {namespace}")
                print(f"🏘️ 검색 지역: {districts_str}")
                print(f"{'='*60}\n")
                
                # 각 검색 결과 상세 출력
                for idx, hit in enumerate(hits, 1):
                    try:
                        print(f"--- 결과 #{idx} ---")
                        print(f"ID: {hit.get('_id', 'N/A')}")
                        print(f"Score: {hit.get('_score', 0):.4f}")
                        
                        if 'fields' in hit:
                            fields = hit['fields']
                            title = fields.get('Title', 'N/A')
                            category = fields.get('Category', 'N/A')
                            chunk_text = fields.get('chunk_text', 'N/A')
                            
                            # 제목과 카테고리 출력
                            print(f"제목: {title}")
                            print(f"카테고리: {category}")
                            
                            # chunk_text 요약 출력 (처음 200자)
                            if chunk_text and chunk_text != 'N/A':
                                preview = chunk_text[:200] + "..." if len(chunk_text) > 200 else chunk_text
                                print(f"내용 미리보기: {preview}")
                        
                        print("")  # 빈 줄로 구분
                        
                    except UnicodeEncodeError:
                        print(f"--- 결과 #{idx} --- [인코딩 오류로 출력 불가]")
                    except Exception as e:
                        print(f"--- 결과 #{idx} --- 출력 중 오류: {str(e)}")
                
                print(f"{'='*60}\n")
            else:
                print(f"\n⚠️ 검색 결과가 없습니다.")
                print(f"검색어: {query}")
                print(f"네임스페이스: {namespace}")
                print(f"검색 지역: {districts_str}\n")
            
            return {
                "source": "pinecone",
                "namespace": namespace,
                "results": ranked_results,
                "status": "success",
                "search_info": search_info
            }
        except Exception as e:
            try:
                print(f"Pinecone search error: {str(e)}")
            except UnicodeEncodeError:
                print("Pinecone search error: [encoding error]")
            return {
                "source": "pinecone",
                "namespace": namespace,
                "results": None,
                "status": "error",
                "error": str(e)
            }
    def process_query(self, query):
        """
        Process a user query through the complete pipeline:
        1. Select the most appropriate namespace
        2. Based on the namespace, either:
           - Query Pinecone if a specific namespace is selected
           - Use Gemini LLM for a direct response if no namespace matches
        """
        # Step 1: Select namespace
        namespace_result = self.select_namespace(query)
        selected_namespace = namespace_result.get('namespace')
        confidence = namespace_result.get('confidence', 0)
        reasoning = namespace_result.get('reasoning', 'No reasoning provided')
        
        # Debug info for namespace selection
        debug_info = {
            "namespace_selection": {
                "selected": selected_namespace,
                "confidence": confidence,
                "reasoning": reasoning
            }
        }
        
        # UTF-8 안전 출력
        try:
            print(f"Selected namespace: {selected_namespace}, confidence: {confidence}")
        except UnicodeEncodeError:
            print("Selected namespace: [encoding error]")
        
        # Step 2: Process based on namespace selection
        if selected_namespace is None:
            # If no appropriate namespace, use LLM to respond directly
            try:
                print("No appropriate namespace found, using LLM directly")
            except UnicodeEncodeError:
                print("No appropriate namespace found, using LLM directly")
            response = self.get_llm_response(query)
            response["debug"] = debug_info
            return response
        else:
            # If namespace selected, query Pinecone with the exact namespace string
            try:
                print(f"Using namespace '{selected_namespace}' for Pinecone search")
            except UnicodeEncodeError:
                print("Using namespace for Pinecone search")
            response = self.search_pinecone(query=query, namespace=selected_namespace)
            response["debug"] = debug_info
            
            # 검색 정보 추가
            if "search_info" in response:
                debug_info["search_info"] = response["search_info"]
                response["debug"] = debug_info
            
            # 결과 구조 확인 및 결과가 있는지 검사
            has_results = False
            if response["status"] == "success" and response.get("results"):
                # 응답 구조 분석
                if "result" in response["results"] and "hits" in response["results"]["result"]:
                    hits = response["results"]["result"]["hits"]
                    if hits and len(hits) > 0:
                        has_results = True
            
            # 결과가 없는 경우 LLM으로 대체
            if not has_results:
                try:
                    print("Pinecone search returned no usable results, falling back to LLM")
                except UnicodeEncodeError:
                    print("Pinecone search returned no usable results, falling back to LLM")
                llm_response = self.get_llm_response(query)
                llm_response["debug"] = debug_info
                
                # 검색 정보 추가
                if "search_info" in response:
                    llm_response["debug"]["search_info"] = response["search_info"]
                
                llm_response["debug"]["pinecone_error"] = "No usable results found"
                return llm_response
            
            return response

# QueryProcessor 인스턴스 생성
query_processor = QueryProcessor(gemini_client, pc, dense_index_name)

@app.route('/query', methods=['POST'])
def query_endpoint():
    try:
        # JSON 요청에서 query 데이터 추출
        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({"error": "Query parameter is required"}), 400
        
        query = data['query']
        
        # UTF-8 안전 출력
        try:
            print(f"받은 질문: {query}")
        except UnicodeEncodeError:
            print("받은 질문: [encoding error]")
        
        # Pinecone 및 Gemini가 초기화되지 않은 경우 더미 데이터 반환
        if pc is None or gemini_client is None:
            return jsonify({
                "query": query,
                "results": [{
                    "id": "test-id-1",
                    "score": 0.95,
                    "title": "테스트 제목",
                    "category": "테스트 카테고리",
                    "content": "API 클라이언트 초기화에 실패했지만 테스트 모드로 실행 중입니다."
                }]
            })
        
        # QueryProcessor를 통해 쿼리 처리
        result = query_processor.process_query(query)
        
        # 결과 형식화 및 반환
        if result["source"] == "llm":
            # LLM 응답 처리
            response_data = {
                "query": query,
                "results": [{
                    "id": "llm-response",
                    "score": 1.0,
                    "title": "AI 응답",
                    "category": "일반 정보",
                    "content": result.get("response", "응답 없음")
                }]
            }
            
            # 디버그 정보 추가 (선택적)
            if "debug" in result:
                if "search_info" in result["debug"]:
                    response_data["district_info"] = {
                        "target_district": result["debug"]["search_info"].get("target_district"),
                        "districts_searched": result["debug"]["search_info"].get("districts_searched", []),
                        "region_type": result["debug"]["search_info"].get("region_type", "unknown")
                    }
                
                response_data["namespace"] = result["debug"]["namespace_selection"].get("selected")
                response_data["confidence"] = result["debug"]["namespace_selection"].get("confidence")
            
            return jsonify(response_data)
        elif result["source"] == "pinecone":
            # Pinecone 결과 처리
            results = []
            
            if result["status"] == "success" and result.get("results") and "result" in result["results"]:
                hits = result["results"]["result"].get("hits", [])
                
                for hit in hits:
                    item = {
                        "id": hit.get('_id', ''),
                        "score": hit.get('_score', 0),
                    }
                    
                    # 필드 정보 추출
                    if 'fields' in hit:
                        fields = hit['fields']
                        item["title"] = fields.get('Title', 'N/A')
                        item["category"] = fields.get('Category', 'N/A')
                        item["content"] = fields.get('chunk_text', 'N/A')
                    
                    results.append(item)
            
            response_data = {
                "query": query,
                "results": results
            }
            
            # 디버그 정보 추가 (선택적)
            if "debug" in result:
                if "search_info" in result["debug"]:
                    response_data["district_info"] = {
                        "target_district": result["debug"]["search_info"].get("target_district"),
                        "districts_searched": result["debug"]["search_info"].get("districts_searched", []),
                        "region_type": result["debug"]["search_info"].get("region_type", "unknown")
                    }
                
                response_data["namespace"] = result["debug"]["namespace_selection"].get("selected")
                response_data["confidence"] = result["debug"]["namespace_selection"].get("confidence")
            
            return jsonify(response_data)
        else:
            # 기타 결과 형식 처리
            return jsonify({
                "query": query,
                "error": "Unknown result source",
                "results": []
            })
            
    except Exception as e:
        import traceback
        try:
            print(f"쿼리 처리 중 오류: {str(e)}")
            print(traceback.format_exc())
        except UnicodeEncodeError:
            print("쿼리 처리 중 오류: [encoding error]")
        return jsonify({
            "query": query if 'query' in locals() else "unknown",
            "error": str(e),
            "results": []
        }), 500


@app.route('/explore', methods=['POST'])
def explore_endpoint():
    try:
        # JSON 요청에서 userCity와 userDistrict 데이터 추출
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        user_city = data.get('userCity', '')
        user_district = data.get('userDistrict', '')
        
        # UTF-8 안전 출력
        try:
            print(f"탐색 요청 받음 - 도시: {user_city}, 구/군: {user_district}")
        except UnicodeEncodeError:
            print("탐색 요청 받음 - [encoding error]")
        
        # 지역 정보가 있는지 확인
        if not user_city and not user_district:
            return jsonify({
                "status": "success",
                "message": "위치 정보가 제공되지 않았습니다.",
                "recommendations": [],
                "generated_query": None,
                "query_response": None
            })
        
        # Multi-query 처리
        generated_query = None
        query_response = None
        actual_llm_query = None  # LLM이 생성한 실제 질문
        
        if user_city and user_district and gemini_client:
            try:
                # 랜덤으로 카테고리 선택
                selected_category = random.choice(list(MULTI_QUERY_CATEGORY.keys()))
                query_template = MULTI_QUERY_CATEGORY[selected_category]
                
                # 템플릿에 실제 위치 정보 채우기 - 이것을 generated_query로 사용
                generated_query = query_template.format(
                    user_city=user_city,
                    user_district=user_district
                )
                
                # Gemini를 사용하여 더 자연스러운 질문 생성
                prompt = f"""
다음 주제에 대해 자연스럽고 구체적인 질문을 하나 만들어주세요.
주제: {generated_query}
카테고리: {selected_category}

시니어(노인)를 위한 정보를 찾는 질문이어야 합니다.
질문만 반환하고 다른 설명은 하지 마세요.
"""
                
                response = gemini_client.models.generate_content(
                model="gemini-1.5-flash",
                    contents=prompt
                )
                
                actual_llm_query = response.text.strip()
                print(f"카테고리: {selected_category}")
                print(f"템플릿 질문: {generated_query}")
                print(f"LLM 생성 질문: {actual_llm_query}")
                
                # LLM이 생성한 질문을 query_processor로 처리
                query_result = query_processor.process_query(actual_llm_query)
                
                # 결과 포맷팅
                if query_result["source"] == "llm":
                    query_response = {
                        "type": "llm",
                        "content": query_result.get("response", "응답 없음"),
                        "category": selected_category  # 카테고리 추가
                    }
                elif query_result["source"] == "pinecone":
                    results = []
                    if query_result["status"] == "success" and query_result.get("results"):
                        if "result" in query_result["results"]:
                            hits = query_result["results"]["result"].get("hits", [])
                            for hit in hits[:3]:  # 상위 3개만
                                if 'fields' in hit:
                                    fields = hit['fields']
                                    results.append({
                                        "title": fields.get('Title', 'N/A'),
                                        "category": fields.get('Category', 'N/A'),
                                        "content": fields.get('chunk_text', 'N/A')[:200] + "..."  # 요약
                                    })
                    
                    query_response = {
                        "type": "pinecone",
                        "results": results,
                        "category": selected_category
                    }
                
            except Exception as e:
                print(f"Multi-query 처리 중 오류: {str(e)}")
        
        # 지역별 추천 검색어 또는 인기 카테고리 생성
        recommendations = []
        
        # 서울시인 경우
        if user_city == "서울특별시" or "서울" in user_city:
            recommendations = [
                f"{user_district} 노인복지관",
                f"{user_district} 경로당",
                f"{user_district} 시니어 일자리",
                f"{user_district} 문화센터 프로그램",
                f"{user_district} 방문요양센터"
            ]
        # 경기도인 경우
        elif user_city == "경기도" or "경기" in user_city:
            recommendations = [
                f"{user_district} 노인복지시설",
                f"{user_district} 실버 일자리",
                f"{user_district} 평생교육원",
                f"{user_district} 주간보호센터",
                f"{user_district} 노인교실"
            ]
        # 인천인 경우
        elif user_city == "인천광역시" or "인천" in user_city:
            recommendations = [
                f"{user_district} 노인복지관",
                f"{user_district} 시니어클럽",
                f"{user_district} 문화강좌",
                f"{user_district} 일자리센터",
                f"{user_district} 경로당"
            ]
        else:
            # 기타 지역
            recommendations = [
                "노인복지시설 찾기",
                "시니어 일자리 정보",
                "문화 프로그램 안내",
                "건강 관리 서비스",
                "여가 활동 정보"
            ]
        
        # 응답 데이터 구성
        response_data = {
            "status": "success",
            "user_location": {
                "city": user_city,
                "district": user_district
            },
            "recommendations": recommendations,
            "popular_searches": [
                "방문요양 서비스",
                "노인 일자리 채용",
                "실버 문화강좌",
                "건강검진 안내",
                "복지관 프로그램"
            ],
            "nearby_facilities": [],  # 추후 구현 가능
            "generated_query": generated_query,  # 템플릿 질문 (위치 정보가 채워진)
            "query_response": query_response  # 질문에 대한 응답
        }
        
        # 지역이 명확한 경우 인접 지역 정보도 추가
        if user_district:
            if user_district in SEOUL_DISTRICT_NEIGHBORS:
                response_data["nearby_districts"] = SEOUL_DISTRICT_NEIGHBORS[user_district][:3]
            elif user_district in GYEONGGI_DISTRICT_NEIGHBORS:
                response_data["nearby_districts"] = GYEONGGI_DISTRICT_NEIGHBORS[user_district][:3]
        
        return jsonify(response_data)
        
    except Exception as e:
        import traceback
        try:
            print(f"탐색 처리 중 오류: {str(e)}")
            print(traceback.format_exc())
        except UnicodeEncodeError:
            print("탐색 처리 중 오류: [encoding error]")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500
    
# 서버 상태 확인용 엔드포인트
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "ok",
        "pinecone": "available" if pc is not None else "unavailable",
        "gemini": "available" if gemini_client is not None else "unavailable"
    })

# 테스트용 홈 엔드포인트
@app.route('/', methods=['GET'])
def home():
    return """
    <html>
    <head>
        <title>지역 기반 통합 검색 서버</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 20px; line-height: 1.6; }
            h1 { color: #333; }
            h2 { color: #555; }
            pre { background: #f4f4f4; padding: 15px; border-radius: 5px; }
            .container { max-width: 800px; margin: 0 auto; }
            .feature { background: #f9f9f9; padding: 15px; margin: 10px 0; border-radius: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>지역 기반 통합 검색 서버</h1>
            <p>서울시와 경기도의 지역 기반 지능형 검색 기능을 제공하는 통합 검색 서버입니다.</p>
            
            <div class="feature">
                <h2>🎯 주요 기능</h2>
                <ul>
                    <li><strong>지역 인식 검색</strong>: 서울시 구 및 경기도 시·군 자동 인식</li>
                    <li><strong>인접 지역 확장</strong>: 해당 지역과 인접한 지역까지 포함하여 검색</li>
                    <li><strong>AI 기반 네임스페이스 선택</strong>: Gemini를 활용한 지능형 카테고리 분류</li>
                    <li><strong>벡터 검색 + LLM</strong>: Pinecone 벡터 검색과 Gemini LLM의 하이브리드 응답</li>
                </ul>
            </div>
            

        </div>
    </body>
    </html>
    """

# 일반 Python 스크립트에서 실행할 때는 이 부분을 사용하세요:
if __name__ == '__main__':
    # Windows 콘솔 한글 지원
    if os.name == 'nt':  # Windows
        import locale
        try:
            locale.setlocale(locale.LC_ALL, 'ko_KR.UTF-8')
        except:
            try:
                locale.setlocale(locale.LC_ALL, 'Korean_Korea.949')
            except:
                pass
    
    port = int(os.getenv("PORT", 5000))
    try:
        print(f"지역 기반 통합 검색 서버를 시작합니다. 포트: {port}")
    except UnicodeEncodeError:
        print("Starting integrated search server...")
    
    app.run(host='0.0.0.0', port=port, debug=True)