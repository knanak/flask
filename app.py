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
    'seoul_job': '서울특별시 고용 정보, 채용 공고, 일자리 관련 데이터',
    'seoul_culture': '서울특별시 문화, 교육, 여가, 평생학습 프로그램 관련 데이터 (세무, 경제, 금융, 컴퓨터, 스마트폰, 건강, 요리, 미술, 음악, 체육, 언어 등 모든 교육 프로그램 포함)', 
    'seoul_facility': '서울특별시 장기요양기관, 방문요양센터, 복지관, 경로당, 노인교실 관련 데이터',
    'kk_job': '경기도 고용 정보, 채용 공고, 일자리 관련 데이터',
    'kk_culture': '경기도 문화, 교육, 여가, 평생학습 프로그램 관련 데이터 (세무, 경제, 금융, 컴퓨터, 스마트폰, 건강, 요리, 미술, 음악, 체육, 언어 등 모든 교육 프로그램 포함)', 
    'kk_facility': '경기도 장기요양기관, 방문요양센터, 복지관, 경로당, 노인교실 관련 데이터',
    'ich_job': '인천 고용 정보, 채용 공고, 일자리 관련 데이터',
    'ich_culture': '인천 문화, 교육, 여가, 평생학습 프로그램 관련 데이터 (세무, 경제, 금융, 컴퓨터, 스마트폰, 건강, 요리, 미술, 음악, 체육, 언어 등 모든 교육 프로그램 포함)', 
    'ich_facility': '인천 장기요양기관, 방문요양센터, 복지관, 경로당, 노인교실 관련 데이터',
    'bs_job': '부산광역시 고용 정보, 채용 공고, 일자리 관련 데이터',
    'bs_culture': '부산광역시 문화, 교육, 여가, 평생학습 프로그램 관련 데이터 (세무, 경제, 금융, 컴퓨터, 스마트폰, 건강, 요리, 미술, 음악, 체육, 언어 등 모든 교육 프로그램 포함)', 
    'bs_facility': '부산광역시 장기요양기관, 방문요양센터, 복지관, 경로당, 노인교실 관련 데이터',
    'kb_job': '경상북도 고용 정보, 채용 공고, 일자리 관련 데이터',
    'kb_culture': '경상북도 문화, 교육, 여가, 평생학습 프로그램 관련 데이터 (세무, 경제, 금융, 컴퓨터, 스마트폰, 건강, 요리, 미술, 음악, 체육, 언어 등 모든 교육 프로그램 포함)', 
    'kb_facility': '경상북도 장기요양기관, 방문요양센터, 복지관, 경로당, 노인교실 관련 데이터',
    'public_health_center' : '서울특별시 보건소, 인천광역시 보건소, 경기도 보건소',
    "workout" : '증상별, 부위별 운동 추천'
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

# 인천시 행정구역 간 인접 정보 (각 구와 인접한 구 목록)
ICH_DISTRICT_NEIGHBORS = {
    '중구': ['동구', '미추홀구', '서구'],
    '동구': ['중구', '미추홀구'],
    '미추홀구': ['중구', '동구', '남동구', '부평구', '서구'],
    '연수구': ['남동구', '서구'],
    '남동구': ['미추홀구', '연수구', '부평구'],
    '부평구': ['미추홀구', '남동구', '계양구', '서구'],
    '계양구': ['부평구', '서구'],
    '서구': ['중구', '미추홀구', '부평구', '계양구', '연수구'],
    '강화군': [],  # 섬 지역으로 다른 구와 육로로 인접하지 않음
    '옹진군': []   # 섬 지역으로 다른 구와 육로로 인접하지 않음
}

# 부산광역시 구·군 간 인접 정보 (각 구·군과 인접한 구·군 목록)
BUSAN_DISTRICT_NEIGHBORS = {
    '중구': ['동구', '서구', '영도구', '부산진구', '남구'],
    '서구': ['중구', '동구', '사하구', '영도구'],
    '동구': ['중구', '서구', '부산진구', '남구'],
    '영도구': ['중구', '서구', '남구', '사하구'],
    '부산진구': ['중구', '동구', '남구', '연제구', '동래구', '북구', '사상구'],
    '동래구': ['부산진구', '연제구', '금정구', '북구', '해운대구'],
    '남구': ['중구', '동구', '영도구', '부산진구', '연제구', '수영구', '해운대구'],
    '북구': ['부산진구', '동래구', '금정구', '사상구', '강서구'],
    '해운대구': ['동래구', '남구', '수영구', '금정구', '기장군'],
    '사하구': ['서구', '영도구', '사상구', '강서구'],
    '금정구': ['동래구', '북구', '해운대구', '기장군'],
    '강서구': ['북구', '사하구', '사상구'],
    '연제구': ['부산진구', '동래구', '남구', '수영구'],
    '수영구': ['남구', '연제구', '해운대구'],
    '사상구': ['부산진구', '북구', '사하구', '강서구'],
    '기장군': ['해운대구', '금정구']
}

# 경상북도 시·군 간 인접 정보 (각 시·군과 인접한 시·군 목록)
GYEONGBUK_DISTRICT_NEIGHBORS = {
    # 북부 지역
    '포항시': ['경주시', '영덕군', '청송군', '영천시', '울산광역시'],
    '경주시': ['포항시', '영천시', '청도군', '울산광역시', '밀양시'],
    '김천시': ['구미시', '칠곡군', '성주군', '거창군', '무주군', '영동군'],
    '안동시': ['영주시', '예천군', '의성군', '청송군', '영양군', '봉화군'],
    '구미시': ['김천시', '칠곡군', '군위군', '의성군', '상주시'],
    '영주시': ['안동시', '봉화군', '예천군', '문경시', '단양군', '영월군'],
    '영천시': ['포항시', '경주시', '청도군', '대구광역시', '경산시', '군위군', '청송군'],
    '상주시': ['구미시', '의성군', '예천군', '문경시', '보은군', '옥천군'],
    '문경시': ['영주시', '예천군', '상주시', '충주시', '제천시', '단양군'],
    '경산시': ['영천시', '청도군', '대구광역시'],
    
    # 군 지역
    '군위군': ['구미시', '의성군', '영천시', '대구광역시'],
    '의성군': ['안동시', '구미시', '군위군', '상주시', '예천군', '청송군'],
    '청송군': ['안동시', '포항시', '영천시', '의성군', '영양군', '영덕군'],
    '영양군': ['안동시', '청송군', '영덕군', '울진군', '봉화군'],
    '영덕군': ['포항시', '청송군', '영양군', '울진군'],
    '청도군': ['경주시', '영천시', '경산시', '대구광역시', '밀양시', '창녕군'],
    '고령군': ['대구광역시', '성주군', '합천군', '창녕군'],
    '성주군': ['김천시', '칠곡군', '고령군', '합천군', '거창군'],
    '칠곡군': ['김천시', '구미시', '성주군', '대구광역시'],
    '예천군': ['안동시', '영주시', '상주시', '문경시', '의성군'],
    '봉화군': ['안동시', '영주시', '영양군', '울진군', '태백시', '삼척시'],
    '울진군': ['영양군', '영덕군', '봉화군', '삼척시'],
    '울릉군': []  # 섬 지역으로 다른 시·군과 육로로 인접하지 않음
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

    def check_location_in_query(self, query):
        """
        LLM을 사용하여 쿼리에 지역명이 있는지 판단합니다.
        """
        if self.gemini_client is None:
            return False
        
        try:
            prompt = f"""
    다음 질문에 한국의 지역명(시/도, 구/군, 동/읍/면 등)이 포함되어 있는지 판단해주세요.

    질문: {query}

    주의사항:
    - "운동", "문화", "프로그램" 등은 일반 명사이므로 지역명이 아닙니다
    - "운동동"처럼 실제 지역명인 경우만 지역명으로 인정합니다
    - 명확한 지역명이 있을 때만 True로 판단하세요

    ### 응답 형식:
    JSON 형식으로 응답해주세요.
    예시: {{"has_location": true, "location": "강북구", "reasoning": "강북구라는 명확한 지역명이 있음"}}
    예시: {{"has_location": false, "location": null, "reasoning": "지역명이 없고 운동 관련 질문만 있음"}}
    """
            
            response = self.gemini_client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=prompt
            )
            
            try:
                result = json.loads(response.text)
                return result.get('has_location', False), result.get('location')
            except json.JSONDecodeError:
                # JSON 파싱 실패시 텍스트에서 판단
                if "true" in response.text.lower() and "has_location" in response.text:
                    return True, None
                return False, None
                
        except Exception as e:
            print(f"지역명 유무 판단 중 오류: {str(e)}")
            return False, None


    def extract_workout_category(self, query):
        """
        운동 관련 질문에서 카테고리(운동 부위나 목적)를 추출합니다.
        """
        # 운동 부위 및 목적 키워드 매핑
        category_mappings = {
            # 신체 부위
            '허리': ['허리', '요추', '척추', '등허리', '허리통증'],
            '어깨': ['어깨', '견갑골', '승모근', '어깨통증'],
            '목': ['목', '경추', '목통증', '거북목'],
            '무릎': ['무릎', '슬개골', '무릎통증', '관절'],
            '발목': ['발목', '발목통증', '족관절'],
            '손목': ['손목', '손목통증', '수근관'],
            '엉덩이': ['엉덩이', '둔부', '고관절', '힙'],
            '복부': ['복부', '뱃살', '복근', '코어'],
            '팔': ['팔', '이두근', '삼두근', '상완'],
            '다리': ['다리', '하체', '종아리', '허벅지'],
            '가슴': ['가슴', '흉근', '대흉근'],
            '등': ['등', '광배근', '등근육'],
            
            # 운동 목적
            '다이어트': ['다이어트', '체중감량', '살빼기', '체지방', '감량'],
            '근력강화': ['근력', '근육', '강화', '벌크업'],
            '유연성': ['유연성', '스트레칭', '유연', '스트레치'],
            '균형': ['균형', '밸런스', '평형'],
            '재활': ['재활', '회복', '치료', '물리치료'],
            '자세교정': ['자세', '교정', '체형', '정렬'],
            '체력': ['체력', '지구력', '스태미나', '심폐'],
            '통증완화': ['통증', '완화', '진통', '아픔']
        }
        
        query_lower = query.lower()
        
        # 각 카테고리에 대해 키워드 매칭
        for category, keywords in category_mappings.items():
            for keyword in keywords:
                if keyword in query_lower:
                    print(f"운동 카테고리 추출: {category} (키워드: {keyword})")
                    return category
        
        # 카테고리를 찾지 못한 경우 Gemini를 사용하여 추출
        if self.gemini_client:
            try:
                prompt = f"""
    다음 운동 관련 질문에서 주요 운동 부위나 목적을 추출해주세요.
    질문: {query}

    가능한 카테고리:
    신체 부위: 허리, 어깨, 목, 무릎, 발목, 손목, 엉덩이, 복부, 팔, 다리, 가슴, 등
    운동 목적: 다이어트, 근력강화, 유연성, 균형, 재활, 자세교정, 체력, 통증완화

    위 카테고리 중 하나만 선택해서 답변해주세요. 
    만약 정확히 일치하는 카테고리가 없다면 가장 관련있는 것을 선택하세요.
    카테고리 이름만 답변해주세요.
    """
                response = self.gemini_client.models.generate_content(
                    model="gemini-2.0-flash-lite",
                    contents=prompt
                )
                
                extracted_category = response.text.strip()
                if extracted_category in category_mappings.keys():
                    print(f"Gemini로 추출한 운동 카테고리: {extracted_category}")
                    return extracted_category
                    
            except Exception as e:
                print(f"운동 카테고리 추출 중 오류: {str(e)}")
        
        return None


    def search_workout_videos(self, query, top_k=10):
        """
        운동 관련 비디오를 검색합니다.
        """
        if self.dense_index is None:
            return {
                "source": "pinecone",
                "namespace": "workout",
                "results": None,
                "status": "error",
                "error": "Pinecone index is not initialized"
            }
        
        try:
            # 1. 카테고리 추출
            category = self.extract_workout_category(query)
            
            # 2. 카테고리가 있으면 필터로 검색
            if category:
                print(f"카테고리 '{category}'로 운동 영상 검색...")
                
                search_params = {
                    "inputs": {"text": query},
                    "top_k": top_k,
                    "filter": {"Category": category}
                }
                
                # 검색 실행
                try:
                    search_result = self.dense_index.search(
                        namespace="workout",
                        query=search_params,
                        fields=["Title", "Category", "Url"],
                        rerank={
                            "model": "bge-reranker-v2-m3",
                            "top_n": 8,
                            "rank_fields": ["Title"]
                        },
                    )
                except Exception as rerank_error:
                    if "maximum token limit" in str(rerank_error):
                        print("토큰 제한 초과. rerank 없이 재시도...")
                        search_result = self.dense_index.search(
                            namespace="workout",
                            query=search_params,
                            fields=["Title", "Category", "Url"]
                        )
                    else:
                        raise rerank_error
                
                # 결과 확인
                if search_result and 'result' in search_result and 'hits' in search_result['result']:
                    hits = search_result['result']['hits']
                    
                    # 결과가 없으면 Title 검색으로 전환
                    if len(hits) == 0:
                        print(f"카테고리 '{category}'에 해당하는 결과가 없습니다. Title 검색으로 전환...")
                        return self._search_workout_by_title(query, top_k)
                    
                    print(f"카테고리 검색 결과: {len(hits)}개 운동 영상 발견")
                    return {
                        "source": "pinecone",
                        "namespace": "workout",
                        "results": {"result": {"hits": hits}},
                        "status": "success",
                        "search_info": {
                            "category": category,
                            "search_type": "category_filter"
                        }
                    }
            
            # 3. 카테고리가 없으면 바로 Title 검색
            else:
                print("카테고리를 추출할 수 없어 Title 검색을 수행합니다...")
                return self._search_workout_by_title(query, top_k)
                
        except Exception as e:
            print(f"운동 영상 검색 중 오류: {str(e)}")
            return {
                "source": "pinecone",
                "namespace": "workout",
                "results": None,
                "status": "error",
                "error": str(e)
            }


    def _search_workout_by_title(self, query, top_k=10):
        """
        Title 필드에서 운동 영상을 검색합니다.
        """
        try:
            # Gemini를 사용하여 검색 키워드 최적화
            if self.gemini_client:
                try:
                    prompt = f"""
    다음 운동 관련 질문에 대해 검색할 키워드를 추출해주세요.
    질문: {query}

    운동 영상 제목에서 찾을 수 있는 핵심 키워드 2-3개를 공백으로 구분해서 제공해주세요.
    예시: "허리 스트레칭 통증"
    """
                    response = self.gemini_client.models.generate_content(
                        model="gemini-2.0-flash-lite",
                        contents=prompt
                    )
                    
                    optimized_query = response.text.strip()
                    print(f"최적화된 검색어: {optimized_query}")
                except:
                    optimized_query = query
            else:
                optimized_query = query
            
            # Title 검색을 위한 파라미터
            search_params = {
                "inputs": {"text": optimized_query},
                "top_k": top_k
            }
            
            # 검색 실행
            try:
                search_result = self.dense_index.search(
                    namespace="workout",
                    query=search_params,
                    fields=["Title", "Category", "Url"],
                    rerank={
                        "model": "bge-reranker-v2-m3",
                        "top_n": 8,
                        "rank_fields": ["Title"]
                    },
                )
            except Exception as rerank_error:
                if "maximum token limit" in str(rerank_error):
                    print("토큰 제한 초과. rerank 없이 재시도...")
                    search_result = self.dense_index.search(
                        namespace="workout",
                        query=search_params,
                        fields=["Title", "Category", "Url"]
                    )
                else:
                    raise rerank_error
            
            if search_result and 'result' in search_result and 'hits' in search_result['result']:
                hits = search_result['result']['hits']
                print(f"Title 검색 결과: {len(hits)}개 운동 영상 발견")
                
                return {
                    "source": "pinecone",
                    "namespace": "workout",
                    "results": {"result": {"hits": hits}},
                    "status": "success",
                    "search_info": {
                        "search_type": "title_search",
                        "optimized_query": optimized_query
                    }
                }
            
            return {
                "source": "pinecone",
                "namespace": "workout",
                "results": {"result": {"hits": []}},
                "status": "success",
                "search_info": {
                    "search_type": "title_search",
                    "message": "검색 결과가 없습니다."
                }
            }
            
        except Exception as e:
            print(f"Title 검색 중 오류: {str(e)}")
            return {
                "source": "pinecone",
                "namespace": "workout",
                "results": None,
                "status": "error",
                "error": str(e)
            }
        
    def select_namespace(self, query, namespace_info=NAMESPACE_INFO):
        """
        지역명이 포함된 쿼리에 대해 Gemini를 사용하여 namespace를 선택합니다.
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
                model="gemini-2.0-flash-lite",
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
                json_match = re.search(r'\{[^}]+\}', response.text, re.DOTALL)
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
                model="gemini-2.0-flash-lite",
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
    
    def is_incheon_namespace(self, namespace):
        """
        네임스페이스가 인천 관련인지 확인합니다.
        """
        return namespace and namespace.startswith('ich')
    
    def is_busan_namespace(self, namespace):
        """
        네임스페이스가 부산 관련인지 확인합니다.
        """
        return namespace and namespace.startswith('bs')

    def is_gyeongbuk_namespace(self, namespace):
        """
        네임스페이스가 경상북도 관련인지 확인합니다.
        """
        return namespace and namespace.startswith('kb')
    
    def extract_district_from_query(self, query, namespace):
        """
        사용자 쿼리에서 지역명을 추출합니다.
        모든 네임스페이스에 대해 통합된 방식으로 지역을 추출합니다.
        
        Args:
            query: 사용자 검색어
            namespace: 선택된 네임스페이스
            
        Returns:
            str: 추출된 지역명 (네임스페이스에 따라 다른 형식)
                - public_health_center: "도시명 구/시/군명" (예: "인천광역시 미추홀구")
                - seoul_*: "구명" (예: "강남구")
                - kk_*: "시/군명" (예: "수원시")
                - ich_*: "구/군명" (예: "미추홀구")
        """
        # 1. 통합 지역 추출 (모든 지역에서 검색)
        extracted_info = self._extract_unified_district(query)
        
        if not extracted_info:
            return None
        
        # 2. 네임스페이스에 따라 적절한 형식으로 반환
        if namespace == "public_health_center":
            # 보건소는 전체 주소 형식 필요
            return extracted_info
        elif self.is_seoul_namespace(namespace):
            # 서울 네임스페이스는 구명만 필요
            if "서울특별시" in extracted_info:
                return extracted_info.replace("서울특별시 ", "")
            return None
        elif self.is_gyeonggi_namespace(namespace):
            # 경기도 네임스페이스는 시/군명만 필요
            if "경기도" in extracted_info:
                return extracted_info.replace("경기도 ", "")
            return None
        elif self.is_incheon_namespace(namespace):
            # 인천 네임스페이스는 구/군명만 필요
            if "인천광역시" in extracted_info:
                return extracted_info.replace("인천광역시 ", "")
            return None
        else:
            # 기타 네임스페이스는 전체 형식 반환
            return extracted_info
        
    def _extract_unified_district(self, query):
        """
        모든 지역(서울, 경기, 인천, 부산, 경북)에서 통합적으로 지역명을 추출합니다.
        
        Returns:
            str: "도시명 구/시/군명" 형식 (예: "부산광역시 해운대구")
        """
        # 1. 모든 지역 목록 생성
        all_districts = []
        district_to_city = {}
        
        # 서울시 구 추가
        for district in SEOUL_DISTRICT_NEIGHBORS.keys():
            all_districts.append(district)
            district_to_city[district] = "서울특별시"
        
        # 경기도 시·군 추가
        for district in GYEONGGI_DISTRICT_NEIGHBORS.keys():
            all_districts.append(district)
            district_to_city[district] = "경기도"
        
        # 인천시 구·군 추가
        for district in ICH_DISTRICT_NEIGHBORS.keys():
            all_districts.append(district)
            district_to_city[district] = "인천광역시"
        
        # 부산시 구·군 추가
        for district in BUSAN_DISTRICT_NEIGHBORS.keys():
            all_districts.append(district)
            district_to_city[district] = "부산광역시"
        
        # 경상북도 시·군 추가
        for district in GYEONGBUK_DISTRICT_NEIGHBORS.keys():
            all_districts.append(district)
            district_to_city[district] = "경상북도"
        
        # 특별 처리: 쿼리에 특정 도시명이 포함되어 있고 동 이름이 있는 경우
        city_keywords = {
            "부산": "부산광역시",
            "서울": "서울특별시",
            "인천": "인천광역시",
            "대구": "대구광역시",
            "광주": "광주광역시",
            "대전": "대전광역시",
            "울산": "울산광역시"
        }
        
        detected_city = None
        for keyword, city_name in city_keywords.items():
            if keyword in query:
                detected_city = city_name
                break
        
        if detected_city:
            dong_pattern = r'(\w+동)'
            dong_matches = re.findall(dong_pattern, query)
            
            if dong_matches and self.gemini_client:
                dong_name = dong_matches[0]
                print(f"{detected_city}에서 동 이름 발견: {dong_name}")
                
                # 해당 도시의 구 목록 가져오기
                city_districts = [d for d, city in district_to_city.items() if city == detected_city]
                
                if city_districts:
                    try:
                        prompt = f"""
    다음 동(洞) 이름이 {detected_city}의 어느 구에 속하는지 정확히 알려주세요.
    동 이름: {dong_name}

    ### {detected_city}의 행정구 목록:
    {", ".join(city_districts)}

    ### 응답 형식:
    JSON 형식으로 응답해주세요: {{"district": "구이름"}}
    만약 {detected_city}에 속하지 않거나 찾을 수 없으면: {{"district": null}}

    ### 예시:
    - 해운대동 → {{"district": "해운대구"}}
    - 중앙동 → {{"district": "중구"}}
    - 광안동 → {{"district": "수영구"}}
    """
                        response = self.gemini_client.models.generate_content(
                            model="gemini-2.0-flash-lite",
                            contents=prompt
                        )
                        
                        try:
                            json_match = re.search(r'\{[^}]+\}', response.text, re.DOTALL)
                            if json_match:
                                result = json.loads(json_match.group(0))
                                district = result.get('district')
                                if district and district in city_districts:
                                    print(f"LLM이 '{dong_name}'이(가) {detected_city} {district}에 속한다고 판단")
                                    return f"{detected_city} {district}"
                        except Exception as e:
                            print(f"LLM 응답 파싱 오류: {str(e)}")
                    
                    except Exception as e:
                        print(f"동 이름으로 구 찾기 중 오류: {str(e)}")
        
        # 2. 쿼리에서 직접 매칭되는 지역명 찾기
        for district in all_districts:
            if district in query:
                city = district_to_city[district]
                print(f"쿼리에서 지역 직접 발견: {city} {district}")
                return f"{city} {district}"
        
        # 3. 정규식으로 구/시/군 패턴 찾기
        patterns = [
            r'(\w+구)',  # XX구
            r'(\w+시)',  # XX시
            r'(\w+군)'   # XX군
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, query)
            for match in matches:
                if match in all_districts:
                    city = district_to_city[match]
                    print(f"정규식으로 지역 발견: {city} {match}")
                    return f"{city} {match}"
        
        # 4. '동' 이름으로 구/시/군 찾기 (도시가 특정되지 않은 경우)
        dong_pattern = r'(\w+동)'
        dong_matches = re.findall(dong_pattern, query)
        
        if dong_matches and self.gemini_client:
            dong_name = dong_matches[0]
            print(f"동 이름 발견: {dong_name}")
            
            try:
                prompt = f"""
    다음 동(洞) 이름이 한국의 어느 지역에 속하는지 정확히 알려주세요.
    동 이름: {dong_name}

    주요 동 이름과 소속 지역 예시:
    - 지제동: 경기도 평택시
    - 역삼동: 서울특별시 강남구
    - 송도동: 인천광역시 연수구
    - 정자동: 경기도 성남시
    - 신촌동: 서울특별시 서대문구
    - 구월동: 인천광역시 남동구
    - 부평동: 인천광역시 부평구
    - 해운대동: 부산광역시 해운대구
    - 서면동: 부산광역시 부산진구
    - 광안동: 부산광역시 수영구

    ### 가능한 행정구역:
    서울특별시: {", ".join([d for d in all_districts if district_to_city[d] == "서울특별시"])}
    경기도: {", ".join([d for d in all_districts if district_to_city[d] == "경기도"])}
    인천광역시: {", ".join([d for d in all_districts if district_to_city[d] == "인천광역시"])}
    부산광역시: {", ".join([d for d in all_districts if district_to_city[d] == "부산광역시"])}
    경상북도: {", ".join([d for d in all_districts if district_to_city[d] == "경상북도"])}

    ### 응답 형식:
    JSON 형식으로 응답해주세요: {{"city": "도시명", "district": "구/시/군명"}}
    찾을 수 없으면: {{"city": null, "district": null}}
    """
                response = self.gemini_client.models.generate_content(
                    model="gemini-2.0-flash-lite",
                    contents=prompt
                )
                
                try:
                    json_match = re.search(r'\{[^}]+\}', response.text, re.DOTALL)
                    if json_match:
                        result = json.loads(json_match.group(0))
                        if result.get('city') and result.get('district'):
                            city = result['city']
                            district = result['district']
                            if district in all_districts:
                                print(f"LLM이 '{dong_name}'이(가) 속한 지역을 찾음: {city} {district}")
                                return f"{city} {district}"
                            else:
                                print(f"LLM이 찾은 '{district}'는 등록된 지역이 아닙니다.")
                except Exception as e:
                    print(f"LLM 응답 파싱 오류: {str(e)}")
                        
            except Exception as e:
                print(f"동 이름으로 지역 추출 중 오류 발생: {str(e)}")
        
        # 5. 지역명 패턴이 없는 경우 LLM으로 분석
        if self.gemini_client:
            try:
                # 쿼리에서 가능한 지역명 추출
                location_words = []
                words = query.split()
                
                for word in words:
                    # 너무 짧은 단어는 제외 (2글자 이상)
                    if len(word) >= 2:
                        # 일반적인 검색어는 제외
                        exclude_words = ['일자리', '복지', '프로그램', '문화', '센터', '시설', '병원', '학교', '마트']
                        if not any(exclude in word for exclude in exclude_words):
                            location_words.append(word)
                
                if location_words:
                    print(f"가능한 지역명 후보: {location_words}")
                    
                    prompt = f"""
    다음 단어들 중에서 한국의 지역명을 찾아주세요.
    단어들: {', '.join(location_words)}

    주요 지역명 예시:
    - 호매실: 경기도 수원시 권선구의 지역명
    - 정자: 경기도 성남시 분당구의 지역명  
    - 판교: 경기도 성남시 분당구의 지역명
    - 송도: 인천광역시 연수구의 지역명
    - 해운대: 부산광역시 해운대구의 지역명
    - 서면: 부산광역시 부산진구의 지역명
    - 광안리: 부산광역시 수영구의 지역명

    ### 가능한 행정구역:
    서울특별시: {", ".join([d for d in all_districts if district_to_city[d] == "서울특별시"])}
    경기도: {", ".join([d for d in all_districts if district_to_city[d] == "경기도"])}
    인천광역시: {", ".join([d for d in all_districts if district_to_city[d] == "인천광역시"])}
    부산광역시: {", ".join([d for d in all_districts if district_to_city[d] == "부산광역시"])}
    경상북도: {", ".join([d for d in all_districts if district_to_city[d] == "경상북도"])}

    ### 응답 형식:
    JSON 형식으로 응답해주세요: {{"location": "지역명", "city": "도시명", "district": "구/시/군명"}}
    지역을 찾을 수 없으면: {{"location": null, "city": null, "district": null}}
    """
                    response = self.gemini_client.models.generate_content(
                        model="gemini-2.0-flash-lite",
                        contents=prompt
                    )
                    
                    try:
                        json_match = re.search(r'\{[^}]+\}', response.text, re.DOTALL)
                        if json_match:
                            result = json.loads(json_match.group(0))
                            if result.get('city') and result.get('district'):
                                city = result['city']
                                district = result['district']
                                location = result.get('location', '')
                                
                                if district in all_districts:
                                    print(f"LLM이 '{location}' 지역을 찾음: {city} {district}")
                                    return f"{city} {district}"
                                else:
                                    print(f"LLM이 찾은 '{district}'는 등록된 지역이 아닙니다.")
                    except Exception as e:
                        print(f"LLM 응답 파싱 오류: {str(e)}")
                            
            except Exception as e:
                print(f"LLM 지역 추출 중 오류 발생: {str(e)}")
        
        # 6. 마지막으로 전체 쿼리를 LLM에 전달하여 지역 추출 시도
        if self.gemini_client:
            try:
                prompt = f"""
    다음 질문에서 한국의 지역명을 추출해주세요.
    질문: {query}

    일반적인 지역명 패턴:
    1. XX시, XX구, XX군, XX동 형태
    2. 지역 이름만 (예: 호매실, 정자, 판교, 일산, 평촌, 해운대, 서면)
    3. 역 이름 (예: 강남역, 홍대입구역) - 역 이름에서 지역 추출

    ### 가능한 행정구역:
    서울특별시: {", ".join([d for d in all_districts if district_to_city[d] == "서울특별시"])}
    경기도: {", ".join([d for d in all_districts if district_to_city[d] == "경기도"])}
    인천광역시: {", ".join([d for d in all_districts if district_to_city[d] == "인천광역시"])}
    부산광역시: {", ".join([d for d in all_districts if district_to_city[d] == "부산광역시"])}
    경상북도: {", ".join([d for d in all_districts if district_to_city[d] == "경상북도"])}

    ### 응답 형식:
    JSON 형식으로 응답해주세요: {{"city": "도시명", "district": "구/시/군명"}}
    지역을 찾을 수 없으면: {{"city": null, "district": null}}
    """
                response = self.gemini_client.models.generate_content(
                    model="gemini-2.0-flash-lite",
                    contents=prompt
                )
                
                try:
                    json_match = re.search(r'\{[^}]+\}', response.text, re.DOTALL)
                    if json_match:
                        result = json.loads(json_match.group(0))
                        if result.get('city') and result.get('district'):
                            city = result['city']
                            district = result['district']
                            if district in all_districts:
                                print(f"LLM으로 지역 추출: {city} {district}")
                                return f"{city} {district}"
                except:
                    pass
                    
            except Exception as e:
                print(f"LLM 지역 추출 중 오류 발생: {str(e)}")
        
        # 지역을 찾지 못한 경우
        print("쿼리에서 지역을 찾을 수 없음")
        return None



    def _extract_seoul_district(self, query):
        """
        서울시 구 이름을 추출합니다.
        동 이름이 포함된 경우, 해당 동이 속한 구를 찾습니다.
        """
        all_districts = list(SEOUL_DISTRICT_NEIGHBORS.keys())
        
        # 정규식 패턴: '구' 글자가 포함된 단어
        pattern = r'(\w+구)'
        matches = re.findall(pattern, query)
        
        # 추출된 '구' 중에서 실제 서울시 구인지 확인
        for match in matches:
            if match in all_districts:
                return match
        
        # '동' 이름이 포함된 경우 확인
        dong_pattern = r'(\w+동)'
        dong_matches = re.findall(dong_pattern, query)
        
        if dong_matches and self.gemini_client:
            # 동 이름이 있는 경우, 해당 동이 속한 구를 찾기
            dong_name = dong_matches[0]
            try:
                prompt = f"""
다음 동(洞) 이름이 서울시의 어느 구에 속하는지 알려주세요.
동 이름: {dong_name}

### 가능한 서울시 구 목록:
{", ".join(all_districts)}

### 응답 형식:
해당 동이 속한 구 이름만 답변해 주세요 (예: "강남구", "종로구").
만약 서울시에 속하지 않거나 찾을 수 없으면 "없음"이라고 답변하세요.

### 참고 정보:
- 삼성동은 강남구에 속합니다
- 명동은 중구에 속합니다
- 신촌동은 서대문구에 속합니다
"""
                response = self.gemini_client.models.generate_content(
                    model="gemini-2.0-flash-lite",
                    contents=prompt
                )
                
                extracted_district = response.text.strip()
                if extracted_district in all_districts:
                    print(f"'{dong_name}'이(가) 속한 구: {extracted_district}")
                    return extracted_district
            except Exception as e:
                print(f"동 이름으로 구 추출 중 오류 발생: {str(e)}")
        
        # Gemini를 통한 일반적인 구 추출 시도
        try:
            prompt = f"""
다음 사용자 질문에서 서울시 행정구역(구 이름)을 추출해주세요.
동(洞) 이름이 있다면 해당 동이 속한 구를 찾아주세요.
만약 특정 구 이름이 없다면 "없음"이라고 답해주세요.

### 사용자 질문:
{query}

### 가능한 서울시 구 목록:
{", ".join(all_districts)}

### 응답 형식:
구 이름만 답변해 주세요 (예: "강남구"). 없으면 "없음"이라고만 답변하세요.
"""
            response = self.gemini_client.models.generate_content(
                model="gemini-2.0-flash-lite",
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
        동 이름이 포함된 경우, 해당 동이 속한 시·군을 찾습니다.
        """
        all_districts = list(GYEONGGI_DISTRICT_NEIGHBORS.keys())
        
        # 정규식 패턴: '시' 또는 '군' 글자가 포함된 단어
        pattern = r'(\w+[시군])'
        matches = re.findall(pattern, query)
        
        # 추출된 시·군 중에서 실제 경기도 시·군인지 확인
        for match in matches:
            if match in all_districts:
                return match
        
        # '동' 이름이 포함된 경우 확인
        dong_pattern = r'(\w+동)'
        dong_matches = re.findall(dong_pattern, query)
        
        if dong_matches and self.gemini_client:
            # 동 이름이 있는 경우, 해당 동이 속한 시·군을 찾기
            dong_name = dong_matches[0]
            try:
                prompt = f"""
다음 동(洞) 이름이 경기도의 어느 시·군에 속하는지 알려주세요.
동 이름: {dong_name}

### 가능한 경기도 시·군 목록:
{", ".join(all_districts)}

### 응답 형식:
해당 동이 속한 시·군 이름만 답변해 주세요 (예: "수원시", "평택시").
만약 경기도에 속하지 않거나 찾을 수 없으면 "없음"이라고 답변하세요.

### 참고 정보:
- 지제동은 평택시에 속합니다
- 정자동은 성남시에 속합니다
- 행신동은 고양시에 속합니다
"""
                response = self.gemini_client.models.generate_content(
                    model="gemini-2.0-flash-lite",
                    contents=prompt
                )
                
                extracted_district = response.text.strip()
                if extracted_district in all_districts:
                    print(f"'{dong_name}'이(가) 속한 시·군: {extracted_district}")
                    return extracted_district
            except Exception as e:
                print(f"동 이름으로 시·군 추출 중 오류 발생: {str(e)}")
        
        # Gemini를 통한 일반적인 시·군 추출 시도
        try:
            prompt = f"""
다음 사용자 질문에서 경기도 행정구역(시 또는 군 이름)을 추출해주세요.
동(洞) 이름이 있다면 해당 동이 속한 시·군을 찾아주세요.
만약 특정 시·군 이름이 없다면 "없음"이라고 답해주세요.

### 사용자 질문:
{query}

### 가능한 경기도 시·군 목록:
{", ".join(all_districts)}

### 응답 형식:
시·군 이름만 답변해 주세요 (예: "수원시", "연천군"). 없으면 "없음"이라고만 답변하세요.
"""
            response = self.gemini_client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=prompt
            )
            
            extracted_district = response.text.strip()
            if extracted_district in all_districts:
                return extracted_district
                
        except Exception as e:
            print(f"경기도 시·군 추출 중 오류 발생: {str(e)}")
        
        return None
    
    def _extract_incheon_district(self, query):
        """
        인천시 구·군 이름을 추출합니다.
        동 이름이 포함된 경우, 해당 동이 속한 구·군을 찾습니다.
        """
        all_districts = list(ICH_DISTRICT_NEIGHBORS.keys())
        
        # 정규식 패턴: '구' 또는 '군' 글자가 포함된 단어
        pattern = r'(\w+[구군])'
        matches = re.findall(pattern, query)
        
        # 추출된 구·군 중에서 실제 인천시 구·군인지 확인
        for match in matches:
            if match in all_districts:
                return match
        
        # '동' 이름이 포함된 경우 확인
        dong_pattern = r'(\w+동)'
        dong_matches = re.findall(dong_pattern, query)
        
        if dong_matches and self.gemini_client:
            # 동 이름이 있는 경우, 해당 동이 속한 구·군을 찾기
            dong_name = dong_matches[0]
            try:
                prompt = f"""
다음 동(洞) 이름이 인천시의 어느 구·군에 속하는지 알려주세요.
동 이름: {dong_name}

### 가능한 인천시 구·군 목록:
{", ".join(all_districts)}

### 응답 형식:
해당 동이 속한 구·군 이름만 답변해 주세요 (예: "연수구", "부평구").
만약 인천시에 속하지 않거나 찾을 수 없으면 "없음"이라고 답변하세요.

### 참고 정보:
- 송도동은 연수구에 속합니다
- 구월동은 남동구에 속합니다
- 부평동은 부평구에 속합니다
"""
                response = self.gemini_client.models.generate_content(
                    model="gemini-2.0-flash-lite",
                    contents=prompt
                )
                
                extracted_district = response.text.strip()
                if extracted_district in all_districts:
                    print(f"'{dong_name}'이(가) 속한 구·군: {extracted_district}")
                    return extracted_district
            except Exception as e:
                print(f"동 이름으로 구·군 추출 중 오류 발생: {str(e)}")
        
        # Gemini를 통한 일반적인 구·군 추출 시도
        try:
            prompt = f"""
다음 사용자 질문에서 인천시 행정구역(구 또는 군 이름)을 추출해주세요.
동(洞) 이름이 있다면 해당 동이 속한 구·군을 찾아주세요.
만약 특정 구·군 이름이 없다면 "없음"이라고 답해주세요.

### 사용자 질문:
{query}

### 가능한 인천시 구·군 목록:
{", ".join(all_districts)}

### 응답 형식:
구·군 이름만 답변해 주세요 (예: "남동구", "강화군"). 없으면 "없음"이라고만 답변하세요.
"""
            response = self.gemini_client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=prompt
            )
            
            extracted_district = response.text.strip()
            if extracted_district in all_districts:
                return extracted_district
                
        except Exception as e:
            print(f"인천 구·군 추출 중 오류 발생: {str(e)}")
        
        return None
    
    def get_nearby_districts(self, district, namespace, max_neighbors=3):
        """
        지정된 지역과 인접한 지역 목록을 반환합니다.
        네임스페이스에 따라 서울, 경기도, 인천, 부산, 경북 인접 정보를 사용합니다.
        """
        if self.is_seoul_namespace(namespace):
            return self._get_seoul_nearby_districts(district, max_neighbors)
        elif self.is_gyeonggi_namespace(namespace):
            return self._get_gyeonggi_nearby_districts(district, max_neighbors)
        elif self.is_incheon_namespace(namespace):
            return self._get_incheon_nearby_districts(district, max_neighbors)
        elif self.is_busan_namespace(namespace):
            return self._get_busan_nearby_districts(district, max_neighbors)
        elif self.is_gyeongbuk_namespace(namespace):
            return self._get_gyeongbuk_nearby_districts(district, max_neighbors)
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
    
    def _get_incheon_nearby_districts(self, district, max_neighbors=3):
        """
        인천시 구·군의 인접 구·군 목록을 반환합니다.
        """
        if not district or district not in ICH_DISTRICT_NEIGHBORS:
            return ['남동구', '부평구', '연수구']  # 기본 인기 지역
        
        neighbors = ICH_DISTRICT_NEIGHBORS.get(district, [])[:max_neighbors]
        # 강화군이나 옹진군처럼 인접 지역이 없는 경우 처리
        if not neighbors:
            # 섬 지역인 경우 다른 주요 구들을 반환
            return [district] + ['남동구', '부평구', '연수구'][:max_neighbors]
        return [district] + neighbors
    

    def _get_busan_nearby_districts(self, district, max_neighbors=3):
        """
        부산시 구·군의 인접 구·군 목록을 반환합니다.
        """
        if not district or district not in BUSAN_DISTRICT_NEIGHBORS:
            return ['해운대구', '부산진구', '남구']  # 기본 인기 지역
        
        neighbors = BUSAN_DISTRICT_NEIGHBORS.get(district, [])[:max_neighbors]
        return [district] + neighbors


    def _get_gyeongbuk_nearby_districts(self, district, max_neighbors=3):
        """
        경상북도 시·군의 인접 시·군 목록을 반환합니다.
        """
        if not district or district not in GYEONGBUK_DISTRICT_NEIGHBORS:
            return ['포항시', '경주시', '안동시']  # 기본 인기 지역
        
        neighbors = GYEONGBUK_DISTRICT_NEIGHBORS.get(district, [])[:max_neighbors]
        # 울릉군처럼 인접 지역이 없는 경우 처리
        if not neighbors:
            return [district] + ['포항시', '경주시', '안동시'][:max_neighbors]
        return [district] + neighbors
    
    def select_relevant_nearby_districts(self, query, target_district, namespace, max_neighbors=3):
        """
        검색어와 관련성이 높은 인접 지역을 선택합니다.
        """
        if self.is_seoul_namespace(namespace):
            return self._select_seoul_relevant_districts(query, target_district, max_neighbors)
        elif self.is_gyeonggi_namespace(namespace):
            return self._select_gyeonggi_relevant_districts(query, target_district, max_neighbors)
        elif self.is_incheon_namespace(namespace):
            return self._select_incheon_relevant_districts(query, target_district, max_neighbors)
        elif self.is_busan_namespace(namespace):
            return self._select_busan_relevant_districts(query, target_district, max_neighbors)
        elif self.is_gyeongbuk_namespace(namespace):
            return self._select_gyeongbuk_relevant_districts(query, target_district, max_neighbors)
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
                model="gemini-2.0-flash-lite",
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
                model="gemini-2.0-flash-lite",
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
    
    def _select_incheon_relevant_districts(self, query, target_district, max_neighbors=3):
        """
        인천시 구·군 기준으로 관련성 높은 인접 구·군을 선택합니다.
        """
        if not target_district or target_district not in ICH_DISTRICT_NEIGHBORS:
            return self._get_incheon_nearby_districts(target_district, max_neighbors)
        
        # 강화군이나 옹진군처럼 인접 지역이 없는 경우 처리
        neighbors_list = ICH_DISTRICT_NEIGHBORS[target_district]
        if not neighbors_list:
            # 섬 지역인 경우 다른 주요 구들을 반환
            return [target_district] + ['남동구', '부평구', '연수구'][:max_neighbors]
        
        try:
            prompt = f"""
사용자가 "{query}"라고 검색했고, 여기서 "{target_district}"를 검색 지역으로 식별했습니다.
다음 인접 구·군 중에서 이 검색어와 가장 관련이 높을 것 같은 구·군을 최대 {max_neighbors}개 선택해주세요:
{neighbors_list}

### 응답 형식:
JSON 형식으로 응답해 주세요. 선택한 구·군 이름만 배열로 제공하세요.
예시: ["구군이름1", "구군이름2", "구군이름3"]
"""
            response = self.gemini_client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=prompt
            )
            
            try:
                neighbors = json.loads(response.text)
                if isinstance(neighbors, list) and all(isinstance(d, str) for d in neighbors):
                    valid_neighbors = [d for d in neighbors if d in ICH_DISTRICT_NEIGHBORS]
                    if valid_neighbors:
                        return [target_district] + valid_neighbors[:max_neighbors]
            except:
                pass
        except Exception as e:
            print(f"인천 인접 구·군 선택 중 오류 발생: {str(e)}")
        
        return self._get_incheon_nearby_districts(target_district, max_neighbors)
    
    def _select_busan_relevant_districts(self, query, target_district, max_neighbors=3):
        """
        부산시 구·군 기준으로 관련성 높은 인접 구·군을 선택합니다.
        """
        if not target_district or target_district not in BUSAN_DISTRICT_NEIGHBORS:
            return self._get_busan_nearby_districts(target_district, max_neighbors)
        
        try:
            prompt = f"""
    사용자가 "{query}"라고 검색했고, 여기서 "{target_district}"를 검색 지역으로 식별했습니다.
    다음 인접 구·군 중에서 이 검색어와 가장 관련이 높을 것 같은 구·군을 최대 {max_neighbors}개 선택해주세요:
    {BUSAN_DISTRICT_NEIGHBORS[target_district]}

    ### 응답 형식:
    JSON 형식으로 응답해 주세요. 선택한 구·군 이름만 배열로 제공하세요.
    예시: ["구군이름1", "구군이름2", "구군이름3"]
    """
            response = self.gemini_client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=prompt
            )
            
            try:
                neighbors = json.loads(response.text)
                if isinstance(neighbors, list) and all(isinstance(d, str) for d in neighbors):
                    valid_neighbors = [d for d in neighbors if d in BUSAN_DISTRICT_NEIGHBORS]
                    if valid_neighbors:
                        return [target_district] + valid_neighbors[:max_neighbors]
            except:
                pass
        except Exception as e:
            print(f"부산 인접 구·군 선택 중 오류 발생: {str(e)}")
        
        return self._get_busan_nearby_districts(target_district, max_neighbors)


    def _select_gyeongbuk_relevant_districts(self, query, target_district, max_neighbors=3):
        """
        경상북도 시·군 기준으로 관련성 높은 인접 시·군을 선택합니다.
        """
        if not target_district or target_district not in GYEONGBUK_DISTRICT_NEIGHBORS:
            return self._get_gyeongbuk_nearby_districts(target_district, max_neighbors)
        
        # 울릉군처럼 인접 지역이 없는 경우 처리
        neighbors_list = GYEONGBUK_DISTRICT_NEIGHBORS[target_district]
        if not neighbors_list:
            return [target_district] + ['포항시', '경주시', '안동시'][:max_neighbors]
        
        try:
            prompt = f"""
    사용자가 "{query}"라고 검색했고, 여기서 "{target_district}"를 검색 지역으로 식별했습니다.
    다음 인접 시·군 중에서 이 검색어와 가장 관련이 높을 것 같은 시·군을 최대 {max_neighbors}개 선택해주세요:
    {neighbors_list}

    ### 응답 형식:
    JSON 형식으로 응답해 주세요. 선택한 시·군 이름만 배열로 제공하세요.
    예시: ["시군이름1", "시군이름2", "시군이름3"]
    """
            response = self.gemini_client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=prompt
            )
            
            try:
                neighbors = json.loads(response.text)
                if isinstance(neighbors, list) and all(isinstance(d, str) for d in neighbors):
                    valid_neighbors = [d for d in neighbors if d in GYEONGBUK_DISTRICT_NEIGHBORS]
                    if valid_neighbors:
                        return [target_district] + valid_neighbors[:max_neighbors]
            except:
                pass
        except Exception as e:
            print(f"경북 인접 시·군 선택 중 오류 발생: {str(e)}")
        
        return self._get_gyeongbuk_nearby_districts(target_district, max_neighbors)

    
    def search_pinecone(self, query, namespace, top_k=10, rerank_top_n=8, user_city=None, user_district=None):
        """
        Search Pinecone vector database using the specified namespace.
        """
        # workout 네임스페이스인 경우 특별 처리 (지역 정보 불필요)
        if namespace == "workout":
            return self.search_workout_videos(query, top_k)
        
        if self.dense_index is None:
            return {
                "source": "pinecone",
                "namespace": namespace,
                "results": None,
                "status": "error",
                "error": "Pinecone index is not initialized"
            }
        
        try:
            print(f"Searching Pinecone with namespace: {namespace}")
            
            # workout이 아닌 경우에만 지역 추출
            target_district_full = self.extract_district_from_query(query, namespace)
            
            # 2. 쿼리에서 지역을 찾지 못했고, 사용자 위치 정보가 있는 경우
            if not target_district_full and user_city and user_district:
                # 네임스페이스에 따라 적절한 형식으로 변환
                if namespace == "public_health_center":
                    target_district_full = f"{user_city} {user_district}".strip()
                elif self.is_seoul_namespace(namespace) and "서울" in user_city:
                    target_district_full = f"서울특별시 {user_district}"
                elif self.is_gyeonggi_namespace(namespace) and "경기" in user_city:
                    target_district_full = f"경기도 {user_district}"
                elif self.is_incheon_namespace(namespace) and "인천" in user_city:
                    target_district_full = f"인천광역시 {user_district}"
                elif self.is_busan_namespace(namespace) and "부산" in user_city:
                    target_district_full = f"부산광역시 {user_district}"
                elif self.is_gyeongbuk_namespace(namespace) and ("경북" in user_city or "경상북도" in user_city):
                    target_district_full = f"경상북도 {user_district}"
                else:
                    # 네임스페이스와 사용자 위치가 일치하지 않는 경우
                    print(f"네임스페이스({namespace})와 사용자 위치({user_city})가 일치하지 않음")
                    target_district_full = None
                
                if target_district_full:
                    print(f"쿼리에서 지역을 찾지 못해 사용자 위치 사용: {target_district_full}")
            
            # 실제 검색에 사용할 지역명 (구/시/군명만)
            target_district = None
            if target_district_full:
                # "부산광역시 수영구" -> "수영구" 형태로 변환
                parts = target_district_full.split()
                if len(parts) >= 2:
                    target_district = parts[-1]  # 마지막 부분이 구/시/군명
                else:
                    target_district = target_district_full
            
            # 3. 지역 정보가 없는 경우 처리
            if not target_district:
                print("지역 정보를 찾을 수 없습니다.")
                # public_health_center는 지역 정보가 필수
                if namespace == "public_health_center":
                    return {
                        "source": "pinecone",
                        "namespace": namespace,
                        "results": None,
                        "status": "error",
                        "error": "지역 정보가 필요합니다. 위치 정보를 제공해주세요."
                    }
                # 다른 네임스페이스는 지역 정보 없이도 검색 가능 (전체 검색)
                else:
                    print(f"{namespace}에서 전체 지역 검색을 수행합니다.")
            
            try:
                print(f"추출된 지역: {target_district if target_district else 'None (전체 검색)'}")
            except UnicodeEncodeError:
                print("추출된 지역: [encoding error]")

            if namespace == "workout":
                return self.search_workout_videos(query, top_k)
            
            # public_health_center의 경우 특별 처리
            if namespace == "public_health_center":
                # public_health_center는 전체 주소 형식 사용
                print(f"보건소 검색 - 대상 지역: {target_district_full}")
                
                search_params = {
                    "inputs": {"text": query},
                    "top_k": top_k,
                    "filter": {"Category": target_district_full}  # 전체 주소 사용
                }
                
                # rerank 없이 먼저 시도
                try:
                    search_result = self.dense_index.search(
                        namespace=namespace,
                        query=search_params,
                        fields=["Title", "Category", "chunk_text"],
                        rerank={
                            "model": "bge-reranker-v2-m3",
                            "top_n": rerank_top_n,
                            "rank_fields": ["chunk_text"]
                        },
                    )
                except Exception as rerank_error:
                    if "maximum token limit" in str(rerank_error):
                        print("토큰 제한 초과. rerank 없이 재시도...")
                        search_result = self.dense_index.search(
                            namespace=namespace,
                            query=search_params,
                            fields=["Title", "Category", "chunk_text"]
                        )
                    else:
                        raise rerank_error
                
                if search_result and 'result' in search_result and 'hits' in search_result['result']:
                    hits = search_result['result']['hits']
                    print(f"보건소 검색 결과: {len(hits)}개")
                    
                    # 검색 정보
                    search_info = {
                        "target_district": target_district_full,
                        "districts_searched": [target_district_full],
                        "districts_available": [],
                        "region_type": "health_center"
                    }
                    
                    return self._format_search_response(
                        namespace, hits, target_district_full, [target_district_full], []
                    )
                else:
                    # 결과가 없는 경우
                    return {
                        "source": "pinecone",
                        "namespace": namespace,
                        "results": {"result": {"hits": []}},
                        "status": "success",
                        "search_info": {
                            "target_district": target_district_full,
                            "districts_searched": [target_district_full],
                            "message": f"{target_district_full} 지역의 보건소 정보를 찾을 수 없습니다."
                        }
                    }
            
            # 일반 네임스페이스 처리
            # 대상 지역과 인접 지역 목록 가져오기
            if target_district:
                districts_to_search = self.select_relevant_nearby_districts(query, target_district, namespace, max_neighbors=3)
            else:
                districts_to_search = []
            
            try:
                districts_str = ', '.join(districts_to_search) if districts_to_search else 'None'
                print(f"검색할 지역 목록: [{districts_str}]")
            except UnicodeEncodeError:
                print("검색할 지역 목록: [encoding error]")
            
            # 1단계: 추출된 지역만으로 우선 검색 (지역이 있는 경우)
            all_results = []
            searched_districts = []
            
            if target_district:
                print(f"\n🔍 1단계: {target_district}에서 우선 검색...")  # 구/시/군명만 출력
                
                search_params = {
                    "inputs": {"text": query},
                    "top_k": top_k,
                    "filter": {"Category": target_district}  # 구/시/군명만 사용
                }
                
                # rerank 시도, 실패하면 rerank 없이
                try:
                    first_search = self.dense_index.search(
                        namespace=namespace,
                        query=search_params,
                        fields=["Title", "Category", "chunk_text"],
                        rerank={
                            "model": "bge-reranker-v2-m3",
                            "top_n": rerank_top_n,
                            "rank_fields": ["chunk_text"]
                        },
                    )
                except Exception as rerank_error:
                    if "maximum token limit" in str(rerank_error):
                        print("토큰 제한 초과. rerank 없이 재시도...")
                        first_search = self.dense_index.search(
                            namespace=namespace,
                            query=search_params,
                            fields=["Title", "Category", "chunk_text"]
                        )
                    else:
                        raise rerank_error
                
                if first_search and 'result' in first_search and 'hits' in first_search['result']:
                    first_hits = first_search['result']['hits']
                    all_results.extend(first_hits)
                    searched_districts.append(target_district)
                    print(f"✅ {target_district}에서 {len(first_hits)}개 결과 발견")
                    
                    # 결과가 8개 이상이면 바로 반환
                    if len(all_results) >= 8:
                        print(f"📊 충분한 결과 확보 (총 {len(all_results)}개)")
                        return self._format_search_response(
                            namespace, all_results, target_district, searched_districts, districts_to_search
                        )
            else:
                # 지역 정보가 없는 경우 전체 검색
                print(f"\n🔍 전체 지역에서 검색...")
                
                search_params = {
                    "inputs": {"text": query},
                    "top_k": top_k
                    # filter 없이 전체 검색
                }
                
                # rerank 시도, 실패하면 rerank 없이
                try:
                    general_search = self.dense_index.search(
                        namespace=namespace,
                        query=search_params,
                        fields=["Title", "Category", "chunk_text"],
                        rerank={
                            "model": "bge-reranker-v2-m3",
                            "top_n": rerank_top_n,
                            "rank_fields": ["chunk_text"]
                        },
                    )
                except Exception as rerank_error:
                    if "maximum token limit" in str(rerank_error):
                        print("토큰 제한 초과. rerank 없이 재시도...")
                        general_search = self.dense_index.search(
                            namespace=namespace,
                            query=search_params,
                            fields=["Title", "Category", "chunk_text"]
                        )
                    else:
                        raise rerank_error
                
                if general_search and 'result' in general_search and 'hits' in general_search['result']:
                    general_hits = general_search['result']['hits']
                    all_results.extend(general_hits)
                    searched_districts.append("전체")
                    print(f"✅ 전체 검색에서 {len(general_hits)}개 결과 발견")
                    
                    return self._format_search_response(
                        namespace, all_results, "전체", ["전체"], []
                    )
            
            # 2단계: 결과가 8개 미만이면 인접 지역에서 추가 검색
            if len(all_results) < 8 and districts_to_search and target_district:
                remaining_districts = [d for d in districts_to_search if d != target_district]
                
                if remaining_districts:
                    needed_results = 8 - len(all_results)
                    print(f"\n🔍 2단계: 추가 {needed_results}개 결과가 필요함. 인접 지역에서 검색...")
                    print(f"검색할 인접 지역: {', '.join(remaining_districts)}")
                    
                    search_params = {
                        "inputs": {"text": query},
                        "top_k": top_k,
                        "filter": {"Category": {"$in": remaining_districts}}
                    }
                    
                    # rerank 시도, 실패하면 rerank 없이
                    try:
                        second_search = self.dense_index.search(
                            namespace=namespace,
                            query=search_params,
                            fields=["Title", "Category", "chunk_text"],
                            rerank={
                                "model": "bge-reranker-v2-m3",
                                "top_n": needed_results,
                                "rank_fields": ["chunk_text"]
                            },
                        )
                    except Exception as rerank_error:
                        if "maximum token limit" in str(rerank_error):
                            print("토큰 제한 초과. rerank 없이 재시도...")
                            second_search = self.dense_index.search(
                                namespace=namespace,
                                query=search_params,
                                fields=["Title", "Category", "chunk_text"]
                            )
                        else:
                            raise rerank_error
                    
                    if second_search and 'result' in second_search and 'hits' in second_search['result']:
                        second_hits = second_search['result']['hits']
                        all_results.extend(second_hits)
                        searched_districts.extend(remaining_districts)
                        print(f"✅ 인접 지역에서 {len(second_hits)}개 추가 결과 발견")
            
            # 최종 결과 반환
            print(f"\n📊 최종 검색 결과: 총 {len(all_results)}개")
            return self._format_search_response(
                namespace, all_results, target_district, searched_districts, districts_to_search
            )
            
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
    
    
    # 10. _format_search_response 메서드의 지역 타입 판별 부분 수정
    def _format_search_response(self, namespace, hits, target_district, searched_districts, all_districts):
        """
        검색 결과를 포맷팅하여 반환합니다.
        """
        # 지역 타입 판별
        if self.is_seoul_namespace(namespace):
            region_type = "seoul"
        elif self.is_gyeonggi_namespace(namespace):
            region_type = "gyeonggi"
        elif self.is_incheon_namespace(namespace):
            region_type = "incheon"
        elif self.is_busan_namespace(namespace):
            region_type = "busan"
        elif self.is_gyeongbuk_namespace(namespace):
            region_type = "gyeongbuk"
        else:
            region_type = "other"
        
        # 검색 정보
        search_info = {
            "target_district": target_district,
            "districts_searched": searched_districts,
            "districts_available": all_districts,
            "region_type": region_type
        }
        
        # 상세한 검색 결과 출력
        if hits:
            result_count = len(hits)
            districts_str = ', '.join(searched_districts) if searched_districts else 'None'
            
            print(f"\n{'='*60}")
            print(f"🔍 검색 결과: 총 {result_count}개 항목")
            print(f"📍 대상 지역: {target_district if target_district else 'None'}")
            print(f"📂 네임스페이스: {namespace}")
            print(f"🏘️ 실제 검색된 지역: {districts_str}")
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
            print(f"네임스페이스: {namespace}")
            print(f"검색된 지역: {', '.join(searched_districts) if searched_districts else 'None'}\n")
        
        # 검색 결과 구조 생성
        ranked_results = {
            'result': {
                'hits': hits
            }
        }
        
        return {
            "source": "pinecone",
            "namespace": namespace,
            "results": ranked_results,
            "status": "success",
            "search_info": search_info
        }
        
    def process_query(self, query, user_city=None, user_district=None):
        """
        Process a user query through the complete pipeline:
        1. Check if query contains location
        2. Select namespace based on location presence and query content
        3. Query Pinecone or use LLM based on namespace
        """
        
        # Step 1: 쿼리에 지역명이 있는지 먼저 판단
        has_location, detected_location = self.check_location_in_query(query)
        
        print(f"지역명 포함 여부: {has_location}")
        if detected_location:
            print(f"감지된 지역: {detected_location}")
        
        # Step 2: 지역명 유무에 따라 다른 처리
        if has_location:
            # 지역명이 있는 경우 - 지역 추출 후 지역 기반 namespace 선택
            extracted_location = self._extract_unified_district(query)
            
            if extracted_location:
                # 지역 기반 namespace 선택
                namespace_result = self.select_namespace_with_location(query, extracted_location)
            else:
                # 지역을 추출하지 못한 경우 일반 namespace 선택
                namespace_result = self.select_namespace(query)
        else:
            # 지역명이 없는 경우 - 키워드 기반 namespace 선택
            namespace_result = self.select_namespace_without_location(query)
            extracted_location = None
        
        selected_namespace = namespace_result.get('namespace')
        confidence = namespace_result.get('confidence', 0)
        reasoning = namespace_result.get('reasoning', 'No reasoning provided')
        
        # Debug info
        debug_info = {
            "namespace_selection": {
                "selected": selected_namespace,
                "confidence": confidence,
                "reasoning": reasoning,
                "has_location": has_location,
                "extracted_location": extracted_location
            }
        }
        
        print(f"Selected namespace: {selected_namespace}, confidence: {confidence}")
        
        # Step 3: Process based on namespace selection
        if selected_namespace is None:
            # No appropriate namespace, use LLM
            print("No appropriate namespace found, using LLM directly")
            response = self.get_llm_response(query)
            response["debug"] = debug_info
            return response
        else:
            # Query Pinecone
            print(f"Using namespace '{selected_namespace}' for Pinecone search")
            
            response = self.search_pinecone(
                query=query, 
                namespace=selected_namespace,
                user_city=user_city,
                user_district=user_district
            )
            response["debug"] = debug_info
            
            # 결과 확인 및 처리 (기존 코드)
            has_results = False
            if response["status"] == "success" and response.get("results"):
                if "result" in response["results"] and "hits" in response["results"]["result"]:
                    hits = response["results"]["result"]["hits"]
                    if hits and len(hits) > 0:
                        has_results = True
            
            if not has_results:
                print("Pinecone search returned no usable results, falling back to LLM")
                llm_response = self.get_llm_response(query)
                llm_response["debug"] = debug_info
                llm_response["debug"]["pinecone_error"] = "No usable results found"
                return llm_response
            
            return response

    def select_namespace_with_location(self, query, extracted_location):

        
        """
        추출된 지역 정보를 고려하여 네임스페이스를 선택합니다.
        """
        # 지역 정보에서 도시 추출
        if "서울특별시" in extracted_location:
            city_prefix = "seoul"
        elif "경기도" in extracted_location:
            city_prefix = "kk"
        elif "인천광역시" in extracted_location:
            city_prefix = "ich"
        elif "부산광역시" in extracted_location:
            city_prefix = "bs"
        elif "경상북도" in extracted_location:
            city_prefix = "kb"
        else:
            # 지역을 알 수 없는 경우 기존 방식으로 처리
            return self.select_namespace(query)

            # 쿼리에서 카테고리 추출을 위해 Gemini 사용
        if self.gemini_client is None:
            return {
                "namespace": None,
                "confidence": 0,
                "reasoning": "Gemini client is not initialized"
            }
        

        
        prompt = f"""
        사용자가 "{extracted_location}"에서 "{query}"에 대해 검색하고 있습니다.
        
        이 검색이 다음 중 어떤 카테고리에 해당하는지 판단해주세요:
        1. job (일자리, 채용, 고용)
        2. culture (문화, 교육, 강좌, 프로그램)
        3. facility (시설, 복지관, 요양원)
        
        ### 응답 형식:
        JSON 형식으로 응답해주세요.
        예시: {{"category": "culture", "confidence": 0.95, "reasoning": "문화 프로그램을 찾고 있음"}}
        """
        
        try:
            response = self.gemini_client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=prompt
            )
            
            # Parse the JSON response
            try:
                result = json.loads(response.text)
                category = result.get('category')
                
                if category:
                    # 도시 prefix와 카테고리를 조합하여 네임스페이스 생성
                    namespace = f"{city_prefix}_{category}"
                    
                    # 네임스페이스가 유효한지 확인
                    if namespace in NAMESPACE_INFO:
                        return {
                            "namespace": namespace,
                            "confidence": result.get('confidence', 0.8),
                            "reasoning": f"{extracted_location}의 {category} 정보를 검색합니다."
                        }
                        
            except json.JSONDecodeError:
                # JSON 파싱 실패 시 텍스트에서 카테고리 추출 시도
                response_text = response.text.lower()
                if "job" in response_text or "일자리" in response_text:
                    category = "job"
                elif "culture" in response_text or "문화" in response_text:
                    category = "culture"
                elif "facility" in response_text or "시설" in response_text:
                    category = "facility"
                else:
                    category = None
                
                if category:
                    namespace = f"{city_prefix}_{category}"
                    if namespace in NAMESPACE_INFO:
                        return {
                            "namespace": namespace,
                            "confidence": 0.7,
                            "reasoning": f"{extracted_location}의 {category} 정보를 검색합니다."
                        }
        
        except Exception as e:
            print(f"네임스페이스 선택 중 오류: {str(e)}")
        
        # 실패한 경우 기존 방식으로 처리
        return self.select_namespace(query)
    
    def select_namespace_without_location(self, query):
        """
        지역명이 없는 쿼리에 대해 적절한 namespace를 선택합니다.
        """
        query_lower = query.lower()
        
        # 운동 관련 키워드 체크
        workout_keywords = [
            '운동', '스트레칭', '요가', '필라테스', '홈트', '홈트레이닝',
            '통증', '재활', '물리치료', '자세교정', '코어',
            '다이어트', '체중감량', '체지방', '근육', '체력',
            '허리', '어깨', '목', '무릎', '발목', '손목',
            '운동법', '운동방법', '운동추천', '운동영상'
        ]
        
        for keyword in workout_keywords:
            if keyword in query_lower:
                return {
                    "namespace": "workout",
                    "confidence": 0.95,
                    "reasoning": f"운동 관련 키워드 '{keyword}'가 포함되어 있어 운동 영상을 검색합니다."
                }
        
        # # 눈 검사 관련 키워드 체크 (지역명이 없어도 보건소 정보가 필요할 수 있음)
        # eye_health_keywords = [
        #     '눈 검사', '안검사', '눈 질환', '시력검사', '안과검진', '눈검진',
        #     '백내장', '녹내장', '황반변성', '안질환', '시력', '안과'
        # ]
        
        # for keyword in eye_health_keywords:
        #     if keyword in query_lower:
        #         # 사용자 위치 정보가 있으면 활용
        #         return {
        #             "namespace": "public_health_center",
        #             "confidence": 0.85,
        #             "reasoning": f"눈/안과 관련 키워드 '{keyword}'가 포함되어 있습니다. 사용자 위치 기반으로 보건소를 검색합니다."
        #         }
        
        # 기타 경우 LLM으로 처리
        return {
            "namespace": None,
            "confidence": 0,
            "reasoning": "특정 카테고리에 해당하지 않아 LLM으로 응답합니다."
        }

    def extract_youtube_video_id(self, url):
        """
        YouTube URL에서 비디오 ID를 추출합니다.
        """
        if not url:
            return None
        
        # 다양한 YouTube URL 형식 처리
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]{11})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None

    def get_youtube_thumbnail_url(self, video_id, quality='hq'):
        """
        YouTube 비디오 ID로부터 썸네일 URL을 생성합니다.
        
        Args:
            video_id: YouTube 비디오 ID
            quality: 썸네일 품질 ('maxres', 'hq', 'mq', 'sd', 'default')
        
        Returns:
            썸네일 URL
        """
        if not video_id:
            return None
        
        quality_map = {
            'maxres': 'maxresdefault',  # 1280x720
            'hq': 'hqdefault',          # 480x360
            'mq': 'mqdefault',          # 320x180
            'sd': 'sddefault',          # 640x480
            'default': 'default'         # 120x90
        }
        
        quality_suffix = quality_map.get(quality, 'hqdefault')
        return f"https://img.youtube.com/vi/{video_id}/{quality_suffix}.jpg"

# QueryProcessor 인스턴스 생성
query_processor = QueryProcessor(gemini_client, pc, dense_index_name)

@app.route('/query', methods=['POST'])
def query_endpoint():
    try:
        # JSON 요청에서 query, userCity, userDistrict 데이터 추출
        data = request.get_json()
        
        if not data or 'query' not in data:
            return jsonify({"error": "Query parameter is required"}), 400
        
        query = data['query']
        user_city = data.get('userCity', '')
        user_district = data.get('userDistrict', '')
        
        # UTF-8 안전 출력
        try:
            print(f"받은 질문: {query}")
            print(f"전체 요청 데이터: {data}") 
            if user_city or user_district:
                print(f"사용자 위치: {user_city} {user_district}")
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
                    "content": "API 클라이언트 초기화에 실패했지만 테스트 모드로 실행 중입니다. | nameSpace: LLM"
                }]
            })
        
        # 체육 시설 이용료 소득 공제 확인
        sports_deduction_keywords = [
            ['체육', '시설', '소득', '공제'],
            ['운동', '시설', '소득', '공제'],
            ['스포츠', '시설', '소득', '공제'],
            ['체육', '이용료', '공제'],
            ['운동', '이용료', '공제'],
            ['헬스장', '소득', '공제'],
            ['헬스장', '세금', '공제'],
            ['체육시설', '세금', '공제'],
            ['운동', '세금', '공제'],
            ['피트니스', '소득', '공제'],
            ['체육시설', '소득공제'],
            ['운동시설', '소득공제']
        ]
        
        # 각 키워드 조합이 모두 포함되어 있는지 확인
        is_sports_deduction_query = False
        for keyword_set in sports_deduction_keywords:
            if all(keyword in query for keyword in keyword_set):
                is_sports_deduction_query = True
                break
        
        # 체육 시설 소득 공제 관련 질문인 경우 즉시 응답
        if is_sports_deduction_query:
            print("체육 시설 이용료 소득 공제 관련 질문 감지")
            return jsonify({
                "query": query,
                "results": [{
                    "id": "sports-deduction-info",
                    "score": 1.0,
                    "title": "체육시설 이용료 소득공제 안내",
                    "category": "체육시설 소득공제",
                    "content": "💪 소득 공제되는 체육시설 확인해보세요![SPORTS_DEDUCTION_URL]https://www.culture.go.kr/deduction/search/list.do#none[/SPORTS_DEDUCTION_URL]"
                }],
                "namespace": "LLM",
                "Query_Category": "체육시설 소득공제"
            })

        # 응급안전안심 서비스 확인
        emergency_keywords = ['응급안전안심', '응급안전', '안심서비스', '독거노인안전', '응급호출', '응급 안전 안심']
        is_emergency_query = any(keyword in query for keyword in emergency_keywords)
        
# /query 엔드포인트의 응급안전안심 처리 부분
        if is_emergency_query:
            print("응급안전안심 서비스 검색 감지")
            
            # 1. QueryProcessor의 _extract_unified_district를 사용하여 위치 추출
            extracted_location = query_processor._extract_unified_district(query)
            
            sido = None
            sigungu = None
            
            if extracted_location:
                # "서울특별시 성북구" 형태를 분리
                parts = extracted_location.split()
                if len(parts) >= 2:
                    sido = parts[0]
                    sigungu = parts[1]
                    print(f"쿼리에서 추출된 위치: {sido} {sigungu}")
            
            # 2. 쿼리에서 위치를 찾지 못한 경우 사용자 위치 정보 사용
            if not sido or not sigungu:
                if user_city and user_district:
                    sido = user_city
                    sigungu = user_district
                    print(f"사용자 위치 사용: {sido} {sigungu}")
            
            # 위치 정보가 없는 경우 에러 반환
            if not sido or not sigungu:
                return jsonify({
                    "query": query,
                    "results": [{
                        "id": "error",
                        "score": 0,
                        "title": "위치 정보 필요",
                        "category": "오류",
                        "content": "응급안전안심서비스 검색을 위해서는 지역 정보가 필요합니다. 예: '성북구 응급안전안심 서비스'"
                    }],
                    "namespace": "emergency_service"
                })
            
            # EmergencyServiceHandler 인스턴스 생성 및 API 호출
            try:
                from emergency_contact import EmergencyServiceHandler
                emergency_handler = EmergencyServiceHandler()
                print("EmergencyServiceHandler 인스턴스 생성 완료")
                
                # 응급안전안심 서비스 검색
                result = emergency_handler.search_emergency_service(sido, sigungu)
                print(f"API 호출 결과 타입: {type(result)}")
                
                # result가 None인지 확인
                if result is None:
                    print("ERROR: search_emergency_service가 None을 반환했습니다!")
                    result = {
                        "status": "error",
                        "error": "API 호출 결과가 None입니다.",
                        "source": "emergency_service"
                    }
                else:
                    print(f"API 호출 결과: {result}")
                    
            except Exception as e:
                print(f"API 호출 중 예외 발생: {str(e)}")
                import traceback
                traceback.print_exc()
                result = {
                    "status": "error",
                    "error": f"API 호출 중 오류: {str(e)}",
                    "source": "emergency_service"
                }
            
            # 결과 포맷팅 - 이제 result는 None이 아님
            if result.get("status") == "success":
                if result.get("results") and len(result["results"]) > 0:
                    # 성공적으로 결과를 받은 경우
                    formatted_results = []
                    for idx, item in enumerate(result["results"]):
                        formatted_result = {
                            "id": f"emergency-{idx}",
                            "score": 1.0,
                            "title": item.get("organNm", "기관명 없음"),
                            "category": f"{result['location']['sido']} {result['location']['sigungu']}",
                            "content": 
                                    f"기관명: {item.get('organNm', '정보 없음')}\n" +
                                    f"주소: {item.get('organAddr', '정보 없음')}\n" +
                                    f"전화: {item.get('organTel', '정보 없음')}\n" +
                                    f"이메일: {item.get('organEmail', '정보 없음')}\n"
                                    # f"사업유형: {item.get('bzType', '정보 없음')}\n" +
                                    # f"기관유형: {item.get('organType', '정보 없음')}"
                        }
                        formatted_results.append(formatted_result)
                    
                    return jsonify({
                        "query": query,
                        "results": formatted_results,
                        "namespace": "emergency_service",
                        "location_filter": f"{result['location']['sido']} {result['location']['sigungu']}",
                        "total_count": result.get("total_count", len(formatted_results))
                    })
                else:
                    # 결과가 없는 경우
                    location_info = result.get('location', {})
                    return jsonify({
                        "query": query,
                        "results": [{
                            "id": "no-result",
                            "score": 0,
                            "title": "검색 결과 없음",
                            "category": f"{location_info.get('sido', '')} {location_info.get('sigungu', '')}",
                            "content": result.get("message", "해당 지역에 등록된 응급안전안심서비스 기관이 없습니다.")
                        }],
                        "namespace": "emergency_service",
                        "location_filter": f"{location_info.get('sido', '')} {location_info.get('sigungu', '')}"
                    })
            else:
                # 오류가 발생한 경우
                return jsonify({
                    "query": query,
                    "results": [{
                        "id": "error",
                        "score": 0,
                        "title": "검색 오류",
                        "category": "오류",
                        "content": result.get("error", "응급안전안심서비스 검색 중 오류가 발생했습니다.")
                    }],
                    "namespace": "emergency_service"
                })
        # 응급안전안심이 아닌 경우 기존 로직 실행
        # QueryProcessor를 통해 쿼리 처리 - 사용자 위치 정보 전달
        result = query_processor.process_query(query, user_city, user_district)
        
        # namespace 결정 - debug 정보에서 가져오기
        selected_namespace = None
        if "debug" in result and "namespace_selection" in result["debug"]:
            selected_namespace = result["debug"]["namespace_selection"].get("selected")
        
        # namespace가 None인 경우 "LLM"으로 설정
        final_namespace = "LLM" if selected_namespace is None else selected_namespace
        
        # public_health_center 네임스페이스인 경우 특별 처리
        if selected_namespace == "public_health_center":
            # search_pinecone의 결과를 이미 받았으므로, 그 결과를 사용
            if result["source"] == "pinecone" and result["status"] == "success":
                results = []
                
                if result.get("results") and "result" in result["results"]:
                    hits = result["results"]["result"].get("hits", [])
                    
                    if hits:
                        # 검색 결과가 있는 경우
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
                        
                        # 검색된 지역 정보 포함
                        location_info = ""
                        if "search_info" in result:
                            target_district = result["search_info"].get("target_district", "")
                            if target_district:
                                location_info = f"{target_district}의 보건소 정보입니다."
                        
                        return jsonify({
                            "query": query,
                            "results": results,
                            "namespace": final_namespace,
                            "location_filter": target_district if "search_info" in result else "",
                            "message": location_info
                        })
                    else:
                        # 해당 지역에 결과가 없는 경우
                        target_district = ""
                        if "search_info" in result:
                            target_district = result["search_info"].get("target_district", "")
                        
                        return jsonify({
                            "query": query,
                            "results": [{
                                "id": "no-result",
                                "score": 0,
                                "title": "검색 결과 없음",
                                "category": target_district,
                                "content": f"{target_district} 지역의 보건소 정보를 찾을 수 없습니다. 인근 지역 보건소를 방문하시거나 지역 보건소에 직접 문의해주세요."
                            }],
                            "namespace": final_namespace,
                            "location_filter": target_district
                        })
                
                # 오류가 발생한 경우
                elif result["status"] == "error":
                    return jsonify({
                        "query": query,
                        "results": [{
                            "id": "error",
                            "score": 0,
                            "title": "검색 오류",
                            "category": "오류",
                            "content": result.get('error', '보건소 정보 검색 중 오류가 발생했습니다.')
                        }],
                        "namespace": final_namespace
                    })
                
        # /query 엔드포인트의 workout namespace 처리 부분
        elif selected_namespace == "workout":
            # workout 네임스페이스인 경우 특별 처리
            if result["source"] == "pinecone" and result["status"] == "success":
                results = []
                
                if result.get("results") and "result" in result["results"]:
                    hits = result["results"]["result"].get("hits", [])
                    
                    if hits:
                        for hit in hits:
                            item = {
                                "id": hit.get('_id', ''),
                                "score": hit.get('_score', 0),
                            }
                            
                            if 'fields' in hit:
                                fields = hit['fields']
                                url = fields.get('Url', '')
                                
                                # YouTube 비디오 ID 추출 및 썸네일 URL 생성
                                video_id = query_processor.extract_youtube_video_id(url)
                                thumbnail_url = None
                                if video_id:
                                    thumbnail_url = query_processor.get_youtube_thumbnail_url(video_id, 'hq')
                                
                                item["title"] = fields.get('Title', 'N/A')
                                item["category"] = fields.get('Category', 'N/A')
                                item["url"] = url
                                item["video_id"] = video_id
                                item["thumbnail_url"] = thumbnail_url
                                item["content"] = f"카테고리: {fields.get('Category', 'N/A')} | 영상 URL: {url}"
                            
                            results.append(item)
                        
                        search_info = result.get("search_info", {})
                        return jsonify({
                            "query": query,
                            "results": results,
                            "namespace": final_namespace,
                            "search_type": search_info.get("search_type", "unknown"),
                            "category": search_info.get("category", "")
                        })
                    else:
                        return jsonify({
                            "query": query,
                            "results": [{
                                "id": "no-result",
                                "score": 0,
                                "title": "검색 결과 없음",
                                "category": "",
                                "content": "해당하는 운동 영상을 찾을 수 없습니다. 다른 검색어로 시도해보세요.",
                                "url": "",
                                "thumbnail_url": None
                            }],
                            "namespace": final_namespace
                        })
        
        # 기존 결과 처리 로직 (public_health_center가 아닌 경우)
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
                    "content": result.get('response', '응답 없음')
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
                
                response_data["namespace"] = final_namespace
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
                
                response_data["namespace"] = final_namespace
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
                model="gemini-2.0-flash-lite",
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
        elif user_city == "부산광역시" or "부산" in user_city:
            recommendations = [
                f"{user_district} 노인복지관",
                f"{user_district} 시니어센터",
                f"{user_district} 평생학습관",
                f"{user_district} 실버일자리",
                f"{user_district} 경로식당"
            ]
        # 경상북도인 경우
        elif user_city == "경상북도" or "경북" in user_city:
            recommendations = [
                f"{user_district} 노인복지시설",
                f"{user_district} 시니어클럽",
                f"{user_district} 문화센터",
                f"{user_district} 일자리지원센터",
                f"{user_district} 복지관"
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
            elif user_district in ICH_DISTRICT_NEIGHBORS:
                neighbors = ICH_DISTRICT_NEIGHBORS[user_district]
                if neighbors:
                    response_data["nearby_districts"] = neighbors[:3]
                else:
                    response_data["nearby_districts"] = ['남동구', '부평구', '연수구'][:3]
            elif user_district in BUSAN_DISTRICT_NEIGHBORS:
                response_data["nearby_districts"] = BUSAN_DISTRICT_NEIGHBORS[user_district][:3]
            elif user_district in GYEONGBUK_DISTRICT_NEIGHBORS:
                neighbors = GYEONGBUK_DISTRICT_NEIGHBORS[user_district]
                if neighbors:
                    response_data["nearby_districts"] = neighbors[:3]
                else:
                    response_data["nearby_districts"] = ['포항시', '경주시', '안동시'][:3]
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
@app.route('/auth/login/kakao', methods=['GET'])
def logiin():
    print('login')
    return jsonify({
        "status": "ok",
        "pinecone": "available" if pc is not None else "unavailable",
        "gemini": "available" if gemini_client is not None else "unavailable"
    })

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
            <h1>지역 기반 통합 검색 서비스</h1>
            <p>서울시, 경기도, 인천시의 지역 기반 지능형 검색 기능을 제공하는 통합 검색 서버입니다.</p>
            
            <div class="feature">
                <h2>🎯 주요 기능</h2>
                <ul>
                    <li><strong>지역 인식 검색</strong>: 서울시 구, 경기도 시·군, 인천시 구·군 자동 인식</li>
                    <li><strong>인접 지역 확장</strong>: 해당 지역과 인접한 지역까지 포함하여 검색</li>
                    <li><strong>AI 기반 네임스페이스 선택</strong>: Gemini를 활용한 지능형 카테고리 분류</li>
                    <li><strong>벡터 검색 + LLM</strong>: Pinecone 벡터 검색과 Gemini LLM의 하이브리드 응답</li>
                    <li><strong>우선 검색 기능</strong>: 추출된 지역을 우선 검색 후 필요시 인접 지역 확장</li>
                </ul>
            </div>
            
            <div class="feature">
                <h2>📍 지원 지역</h2>
                <ul>
                    <li><strong>서울특별시</strong>: 25개 구</li>
                    <li><strong>경기도</strong>: 31개 시·군</li>
                    <li><strong>인천광역시</strong>: 8개 구, 2개 군 (강화군, 옹진군 포함)</li>
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