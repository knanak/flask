from flask import Flask, request, jsonify
import os
import json
import traceback
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
            response = self.gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"""
사용자 질문에 대해 직접 답변해주세요:
{query}
"""
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
    
    def generate_fallback_queries(self, query):
        """
        사용자 쿼리를 분석하여 대체 검색어를 생성하는 함수
        
        전략:
        1. 지역만 포함한 더 넓은 범위의 검색어 (예: "강북구 일자리")
        2. 직업만 포함한 더 넓은 범위의 검색어 (예: "미화원 일자리")
        3. 인접 지역에서의 같은 직업 검색어 (예: "도봉구 미화원 일자리")
        """
        # 기본 대체 쿼리 목록 (직접 구현)
        fallback_queries = []
        
        # 검색어 분석 - 지역명과 직업명 추출 시도
        try:
            # 서울 구 목록
            seoul_districts = ["강남구", "강동구", "강북구", "강서구", "관악구", "광진구", "구로구", "금천구",
                            "노원구", "도봉구", "동대문구", "동작구", "마포구", "서대문구", "서초구",
                            "성동구", "성북구", "송파구", "양천구", "영등포구", "용산구", "은평구", "종로구", "중구", "중랑구"]
            
            # 인접 구 정보 (주요 인접 구 매핑)
            adjacent_districts = {
                "강남구": ["서초구", "송파구", "강동구", "성동구"],
                "강동구": ["송파구", "강남구", "광진구"],
                "강북구": ["도봉구", "노원구", "성북구"],
                "강서구": ["양천구", "구로구", "마포구"],
                "관악구": ["동작구", "서초구", "금천구"],
                "광진구": ["성동구", "중랑구", "강동구"],
                "구로구": ["금천구", "영등포구", "양천구", "강서구"],
                "금천구": ["구로구", "관악구", "영등포구"],
                "노원구": ["도봉구", "강북구", "중랑구"],
                "도봉구": ["강북구", "노원구"],
                "동대문구": ["성북구", "중랑구", "성동구"],
                "동작구": ["관악구", "서초구", "영등포구", "용산구"],
                "마포구": ["서대문구", "용산구", "영등포구", "강서구"],
                "서대문구": ["은평구", "마포구", "종로구"],
                "서초구": ["강남구", "동작구", "관악구"],
                "성동구": ["동대문구", "광진구", "중구", "용산구"],
                "성북구": ["강북구", "동대문구", "종로구"],
                "송파구": ["강동구", "강남구"],
                "양천구": ["강서구", "구로구", "영등포구"],
                "영등포구": ["구로구", "양천구", "마포구", "동작구", "금천구"],
                "용산구": ["중구", "성동구", "마포구", "동작구", "서초구"],
                "은평구": ["서대문구", "종로구"],
                "종로구": ["중구", "서대문구", "성북구", "동대문구"],
                "중구": ["종로구", "성동구", "용산구", "동대문구"],
                "중랑구": ["동대문구", "광진구", "노원구"]
            }
            
            # 일반적인 직업 키워드
            job_keywords = ["미화원", "경비원", "사무원", "경리", "행정", "상담원", "판매원", "영업", "교사", 
                        "강사", "요양보호사", "간호", "조리", "주방", "안내원", "청소", "경호원", "운전", "배달"]
            
            # 쿼리에서 구 이름 찾기
            district = None
            for d in seoul_districts:
                if d in query:
                    district = d
                    break
            
            # 쿼리에서 직업 키워드 찾기
            job = None
            for j in job_keywords:
                if j in query:
                    job = j
                    break
            
            print(f"분석 결과 - 지역: {district}, 직업: {job}")
            
            # 대체 쿼리 생성 1: 지역만 포함한 더 넓은 범위의 검색어
            if district:
                fallback_queries.append(f"{district} 일자리")
            
            # 대체 쿼리 생성 2: 직업만 포함한 더 넓은 범위의 검색어
            if job:
                fallback_queries.append(f"{job} 일자리")
            
            # 대체 쿼리 생성 3: 인접 지역의 같은 직업 검색어
            if district and job and district in adjacent_districts:
                for adj_district in adjacent_districts[district]:
                    fallback_queries.append(f"{adj_district} {job} 일자리")
            
        except Exception as e:
            print(f"Error generating fallback queries: {str(e)}")
        
        # 대체 쿼리가 없으면 기본 쿼리 추가
        if not fallback_queries:
            if "일자리" in query:
                fallback_queries.append("서울시 일자리")
            if "문화" in query:
                fallback_queries.append("서울시 문화 프로그램")
        
        print(f"생성된 대체 쿼리: {fallback_queries}")
        return fallback_queries
    
    def search_pinecone_with_fallback(self, query, namespace, top_k=10, rerank_top_n=2):
        """
        Search Pinecone vector database with fallback strategies for better results.
        
        Fallback strategies:
        1. If no results for specific query (e.g., "강북구 미화원 일자리"), try broader location query (e.g., "강북구 일자리")
        2. If still no results, try same job in adjacent districts (e.g., "도봉구 미화원 일자리")
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
            
            # 1. 원래 쿼리로 검색 시도
            ranked_results = self.dense_index.search(
                namespace=namespace,
                query={
                    "inputs": {"text": query},
                    "top_k": top_k
                },
                rerank={
                    "model": "bge-reranker-v2-m3",
                    "top_n": rerank_top_n,
                    "rank_fields": ["chunk_text"]
                },
                fields=["Title", "Category", "chunk_text"]
            )
            
            # 검색 결과 확인
            has_results = False
            if "result" in ranked_results and "hits" in ranked_results["result"]:
                hits = ranked_results["result"]["hits"]
                if hits and len(hits) > 0:
                    has_results = True
                    print(f"Found {len(hits)} results for original query: {query}")
            
            # 검색 결과가 없는 경우 대체 전략 실행
            if not has_results:
                print(f"No results found for '{query}'. Trying fallback strategies...")
                
                # 쿼리 분석을 위해 대체 쿼리 생성
                fallback_queries = self.generate_fallback_queries(query)
                
                all_hits = []
                
                # 각 대체 쿼리로 검색 시도
                for fallback_query in fallback_queries:
                    print(f"Trying fallback query: {fallback_query}")
                    
                    try:
                        fallback_results = self.dense_index.search(
                            namespace=namespace,
                            query={
                                "inputs": {"text": fallback_query},
                                "top_k": top_k
                            },
                            rerank={
                                "model": "bge-reranker-v2-m3",
                                "top_n": rerank_top_n,
                                "rank_fields": ["chunk_text"]
                            },
                            fields=["Title", "Category", "chunk_text"]
                        )
                        
                        # 결과 확인 및 병합
                        if "result" in fallback_results and "hits" in fallback_results["result"]:
                            fallback_hits = fallback_results["result"]["hits"]
                            if fallback_hits and len(fallback_hits) > 0:
                                print(f"Found {len(fallback_hits)} results for fallback query: {fallback_query}")
                                
                                # 각 결과에 사용된 대체 쿼리 정보 추가
                                for hit in fallback_hits:
                                    if "fields" not in hit:
                                        hit["fields"] = {}
                                    hit["fields"]["fallback_query"] = fallback_query
                                
                                all_hits.extend(fallback_hits)
                                
                    except Exception as e:
                        print(f"Error searching with fallback query '{fallback_query}': {str(e)}")
                
                # 대체 쿼리로 찾은 결과가 있으면 기존 ranked_results 구조에 병합
                if all_hits:
                    has_results = True
                    
                    # 결과 점수 순으로 정렬 (내림차순)
                    all_hits.sort(key=lambda x: x.get('_score', 0), reverse=True)
                    
                    # 최대 rerank_top_n개만 유지
                    all_hits = all_hits[:rerank_top_n]
                    
                    # 새로운 결과 구조 생성
                    if "result" not in ranked_results:
                        ranked_results["result"] = {}
                    
                    ranked_results["result"]["hits"] = all_hits
                    print(f"Combined {len(all_hits)} results from fallback queries")
            
            return {
                "source": "pinecone",
                "namespace": namespace,
                "results": ranked_results,
                "status": "success" if has_results else "no_results"
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
        Process a user query through the complete pipeline with improved fallback strategies.
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
            # If namespace selected, query Pinecone with the improved search function
            print(f"Using namespace '{selected_namespace}' for Pinecone search")
            response = self.search_pinecone_with_fallback(query=query, namespace=selected_namespace)
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
                llm_response["debug"]["pinecone_error"] = "No usable results found even with fallback strategies"
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
            return jsonify({
                "query": query,
                "results": [{
                    "id": "llm-response",
                    "score": 1.0,
                    "title": "AI 응답",
                    "category": "일반 정보",
                    "content": result.get("response", "응답 없음")
                }]
            })
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
                        
                        # 대체 쿼리 정보가 있으면 추가
                        if 'fallback_query' in fields:
                            item["fallback_query"] = fields.get('fallback_query')
                    
                    results.append(item)
                
                # 대체 쿼리로 검색된 결과가 있을 경우 메타 정보 추가
                has_fallback = any('fallback_query' in item for item in results)
                if has_fallback:
                    # 응답에 대체 쿼리로 검색되었음을 알리는 메타 정보 추가
                    return jsonify({
                        "query": query,
                        "results": results,
                        "meta": {
                            "used_fallback": True,
                            "note": "정확한 검색 결과가 없어 유사한 결과를 제공합니다."
                        }
                    })
            
            return jsonify({
                "query": query,
                "results": results
            })
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
            "query": query,
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
            
            <h2>개선된 검색 기능</h2>
            <p>특정 검색어(예: "강북구 미화원 일자리")에 일치하는 결과가 없는 경우:</p>
            <ol>
                <li>지역만 포함한 더 넓은 범위의 검색을 시도합니다. (예: "강북구 일자리")</li>
                <li>인접 지역의 같은 직업을 검색합니다. (예: "도봉구 미화원 일자리")</li>
            </ol>
            
            <h2>사용 방법</h2>
            <p>다음과 같이 /query 엔드포인트로 POST 요청을 보내세요:</p>
            
            <pre>
    curl -X POST \\
      http://localhost:5000/query \\
      -H 'Content-Type: application/json' \\
      -d '{
        "query": "강북구 미화원 일자리"
    }'
            </pre>
            
            <h2>엔드포인트</h2>
            <ul>
                <li><strong>/query</strong> - 질문을 처리하는 메인 엔드포인트</li>
                <li><strong>/health</strong> - 서버 상태 확인용 엔드포인트</li>
            </ul>
        </div>
    </body>
    </html>
    """

# 일반 Python 스크립트에서 실행할 때는 이 부분을 사용하세요:
if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    print(f"서버를 시작합니다. 포트: {port}")
    app.run(host='0.0.0.0', port=port)