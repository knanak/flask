from flask import Flask, request, jsonify
import os
import json
import traceback
import re
from threading import Thread
from dotenv import load_dotenv

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
    'kk_job_data': '경기도 고용 정보, 채용 공고, 일자리 관련 데이터',
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
                model="gemini-2.0-flash",
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
                import re
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
                model="gemini-2.0-flash",
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
    
    def extract_district_from_query(self, query):
        """
        사용자 쿼리에서 서울시 행정구역(구 이름)을 추출합니다.
        
        Args:
            query: 사용자 검색어
            
        Returns:
            str: 추출된 구 이름 (없으면 None)
        """
        if self.gemini_client is None:
            return None
            
        # 서울시 모든 구 이름 목록 (SEOUL_DISTRICT_NEIGHBORS의 키 목록)
        all_districts = list(SEOUL_DISTRICT_NEIGHBORS.keys())
        
        # 정규식 패턴: '구' 글자가 포함된 단어
        pattern = r'(\w+구)'
        matches = re.findall(pattern, query)
        
        # 추출된 '구' 중에서 실제 서울시 구인지 확인
        for match in matches:
            if match in all_districts:
                return match
        
        # 구체적인 구 이름을 찾지 못한 경우, Gemini에게 구 정보 추출 요청
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
                model="gemini-2.0-flash",
                contents=prompt
            )
            
            extracted_district = response.text.strip()
            if extracted_district in all_districts:
                return extracted_district
            
        except Exception as e:
            print(f"구 추출 중 오류 발생: {str(e)}")
        
        # 기본값: 구를 찾지 못함
        return None
    
    def get_nearby_districts(self, district, max_neighbors=3):
        """
        지정된 구와 인접한 구 목록을 반환합니다.
        
        Args:
            district: 기준이 되는 구 이름
            max_neighbors: 최대 인접 구 수
            
        Returns:
            list: 인접 구 목록 (기준 구 포함)
        """
        # 구 이름이 없거나 인접 정보가 없으면 기본 구 목록 반환
        if not district or district not in SEOUL_DISTRICT_NEIGHBORS:
            return ['강남구', '서초구', '종로구']  # 기본 인기 지역
        
        # 기준 구와 인접 구 목록 생성 (최대 max_neighbors개)
        neighbors = SEOUL_DISTRICT_NEIGHBORS.get(district, [])[:max_neighbors]
        
        # 기준 구를 포함한 리스트 반환
        return [district] + neighbors
    
    def select_relevant_nearby_districts(self, query, target_district, max_neighbors=3):
        """
        검색어와 관련성이 높은 인접 구를 선택합니다.
        
        Args:
            query: 사용자 검색어
            target_district: 기준 구 이름
            max_neighbors: 최대 인접 구 수
            
        Returns:
            list: 관련성 높은 인접 구 목록 (기준 구 포함)
        """
        if self.gemini_client is None or not target_district or target_district not in SEOUL_DISTRICT_NEIGHBORS:
            return self.get_nearby_districts(target_district, max_neighbors)
        
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
                model="gemini-2.0-flash",
                contents=prompt
            )
            
            try:
                # 응답 파싱 시도
                neighbors = json.loads(response.text)
                if isinstance(neighbors, list) and all(isinstance(d, str) for d in neighbors):
                    # 유효한 구 이름만 필터링
                    valid_neighbors = [d for d in neighbors if d in SEOUL_DISTRICT_NEIGHBORS]
                    if valid_neighbors:
                        # 기준 구를 목록 맨 앞에 추가
                        return [target_district] + valid_neighbors[:max_neighbors]
            except:
                # 파싱 실패 시 기본 인접 구 사용
                pass
        except Exception as e:
            print(f"인접 구 선택 중 오류 발생: {str(e)}")
        
        # 기본 인접 구 반환
        return self.get_nearby_districts(target_district, max_neighbors)
    
    def search_pinecone(self, query, namespace, top_k=10, rerank_top_n=2):
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
            print(f"Searching Pinecone with namespace: {namespace}")
            
            # 검색어에서 구 이름 추출
            target_district = self.extract_district_from_query(query)
            print(f"추출된 구: {target_district}")
            
            # 대상 구와 인접 구 목록 가져오기 (관련성 기반 선택)
            districts_to_search = self.select_relevant_nearby_districts(query, target_district, max_neighbors=3)
            print(f"검색할 구 목록: {districts_to_search}")
            
            # 검색 필터 구성
            search_filter = None
            if districts_to_search:
                search_filter = {"Category": {"$in": districts_to_search}}
            
            # 원래 제공된 형식 그대로 검색 실행, 필터 추가
            search_params = {
                "inputs": {"text": query},
                "top_k": top_k  # 먼저 더 많은 결과를 가져온 다음 리랭킹
            }
            
            # 필터가 있는 경우에만 추가
            if search_filter:
                search_params["filter"] = search_filter
            
            ranked_results = self.dense_index.search(
                namespace=namespace,  # 선택된 namespace 사용
                query=search_params,
                fields=["Title", "Category", "chunk_text"],  # 반환할 필드 지정
                rerank={
                    "model": "bge-reranker-v2-m3",  # BGE-Reranker-v2-m3 모델 사용
                    "top_n": rerank_top_n,  # 상위 N개 결과만 반환
                    "rank_fields": ["chunk_text"]  # chunk_text 필드를 사용하여 리랭킹
                }
            )
            
            # 검색 정보를 디버그 정보에 추가
            search_info = {
                "target_district": target_district,
                "districts_searched": districts_to_search
            }
            
            # 결과 확인을 위한 디버그 정보 추가
            print(f"Search results: {ranked_results}")
            
            return {
                "source": "pinecone",
                "namespace": namespace,
                "results": ranked_results,
                "status": "success",
                "search_info": search_info
            }
        except Exception as e:
            print(f"Pinecone search error: {str(e)}")
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
        
        print(f"Selected namespace: {selected_namespace}, confidence: {confidence}")
        
        # Step 2: Process based on namespace selection
        if selected_namespace is None:
            # If no appropriate namespace, use LLM to respond directly
            print("No appropriate namespace found, using LLM directly")
            response = self.get_llm_response(query)
            response["debug"] = debug_info
            return response
        else:
            # If namespace selected, query Pinecone with the exact namespace string
            print(f"Using namespace '{selected_namespace}' for Pinecone search")
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
                print(f"Pinecone search returned no usable results, falling back to LLM")
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
        print(f"받은 질문: {query}")
        
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
                        "districts_searched": result["debug"]["search_info"].get("districts_searched", [])
                    }
                
                response_data["namespace"] = result["debug"]["namespace_selection"].get("selected")
            
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
                        "districts_searched": result["debug"]["search_info"].get("districts_searched", [])
                    }
                
                response_data["namespace"] = result["debug"]["namespace_selection"].get("selected")
            
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
        print(f"쿼리 처리 중 오류: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            "query": query if 'query' in locals() else "unknown",
            "error": str(e),
            "results": []
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
        <title>통합 검색 서버</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 20px; line-height: 1.6; }
            h1 { color: #333; }
            pre { background: #f4f4f4; padding: 15px; border-radius: 5px; }
            .container { max-width: 800px; margin: 0 auto; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>통합 검색 서버</h1>
            <p>통합 검색 서버가 실행 중입니다. Pinecone 데이터베이스 검색 및 Gemini LLM을 활용한 응답을 제공합니다.</p>
            <p>지역 기반 지능형 검색 기능이 적용되어 있습니다. 특정 구를 언급하면 해당 구와 관련성 높은 인접 구들의 정보도 함께 검색합니다.</p>
            
        </div>
    </body>
    </html>
    """

# 일반 Python 스크립트에서 실행할 때는 이 부분을 사용하세요:
if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    print(f"서버를 시작합니다. 포트: {port}")
    app.run(host='0.0.0.0', port=port)