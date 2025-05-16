from flask import Flask, request, jsonify
import os
from threading import Thread
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드
load_dotenv()

app = Flask(__name__)

# Pinecone API 키
api_key = os.getenv("PINECONE_API_KEY")
if not api_key:
    print("경고: PINECONE_API_KEY가 설정되지 않았습니다.")
    api_key = "dummy_key_for_testing"  # 테스트용 더미 키

# 인덱스 이름
dense_index_name = os.getenv("PINECONE_INDEX_NAME", "dense-for-hybrid-py")

# Pinecone 모듈 및 클라이언트 초기화
try:
    from pinecone import Pinecone
    pc = Pinecone(api_key=api_key)
    print("Pinecone 클라이언트 초기화 성공")
except ImportError:
    print("Pinecone 라이브러리를 찾을 수 없습니다. pip install pinecone-client로 설치하세요.")
    pc = None
except Exception as e:
    print(f"Pinecone 초기화 중 오류: {str(e)}")
    pc = None

@app.route('/query', methods=['POST'])
def query_pinecone():
    try:
        # JSON 요청에서 query 데이터 추출
        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({"error": "Query parameter is required"}), 400
        
        query = data['query']
        print(f"받은 질문: {query}")
        
        # Pinecone이 초기화되지 않은 경우 더미 데이터 반환
        if pc is None:
            return jsonify({
                "query": query,
                "results": [{
                    "id": "test-id-1",
                    "score": 0.95,
                    "title": "테스트 제목",
                    "category": "테스트 카테고리",
                    "content": "Pinecone 연결이 실패했지만 테스트 모드로 실행 중입니다."
                }]
            })
        
        # Pinecone 인덱스 접근
        try:
            dense_index = pc.Index(dense_index_name)
            
            # 검색 쿼리와 함께 리랭킹 수행
            ranked_results = dense_index.search(
                namespace="example-namespace",
                query={
                    "inputs": {"text": query},
                    "top_k": 10
                },
                rerank={
                    "model": "bge-reranker-v2-m3",
                    "top_n": 2,
                    "rank_fields": ["chunk_text"]
                },
                fields=["Title", "Category", "chunk_text"]
            )
            print(ranked_results)
            
            # 결과 처리 - 새로운 형식으로 처리
            results = []
            
            # ranked_results 구조에서 필요한 정보 추출
            if 'result' in ranked_results and 'hits' in ranked_results['result']:
                hits = ranked_results['result']['hits']
                
                for hit in hits:
                    result = {
                        "id": hit.get('_id', ''),
                        "score": hit.get('_score', 0),
                    }
                    
                    # 필드 정보 추출
                    if 'fields' in hit:
                        fields = hit['fields']
                        result["title"] = fields.get('Title', 'N/A')
                        result["category"] = fields.get('Category', 'N/A')
                        result["content"] = fields.get('chunk_text', 'N/A')
                    
                    results.append(result)
            
            return jsonify({
                "query": query,
                "results": results
            })
            
        except Exception as e:
            import traceback
            print(f"Pinecone 검색 중 오류: {str(e)}")
            print(traceback.format_exc())
            return jsonify({
                "query": query,
                "error": str(e),
                "results": []
            }), 500
    
    except Exception as e:
        import traceback
        print(f"쿼리 처리 중 오류: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# 서버 상태 확인용 엔드포인트
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok"})

# 테스트용 홈 엔드포인트
@app.route('/', methods=['GET'])
def home():
    return "Pinecone 검색 서버가 실행 중입니다. /query 엔드포인트로 POST 요청을 보내세요."

# 일반 Python 스크립트에서 실행할 때는 이 부분을 사용하세요:
if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    print(f"서버를 시작합니다. 포트: {port}")
    app.run(host='0.0.0.0', port=port)