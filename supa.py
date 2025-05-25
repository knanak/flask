import os
import pandas as pd
from supabase import create_client, Client
import glob
from datetime import datetime

# Supabase 설정
SUPABASE_URL = "https://ptztivxympkpwiwdlcit.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# CSV 파일이 있는 폴더 경로
CSV_FOLDER_PATH = "path/to/your/csv/folder"

# 통합 CSV 파일 저장 경로
MERGED_CSV_PATH = "path/to/your/csv/folder/merged_kk_facility.csv"

# Supabase 클라이언트 생성
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def create_table_if_not_exists(table_name='kk_facility2'):
    """
    테이블이 없으면 생성 (RPC 함수 사용)
    """
    try:
        # 먼저 테이블이 있는지 확인
        response = supabase.table(table_name).select("*").limit(1).execute()
        print(f"테이블 '{table_name}'이 이미 존재합니다.")
        return True
    except Exception as e:
        if "relation" in str(e) and "does not exist" in str(e):
            print(f"테이블 '{table_name}'이 없습니다. 생성을 시도합니다...")
            
            # SQL 쿼리로 테이블 생성 (RPC 함수 필요)
            create_table_query = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                "Id" INTEGER PRIMARY KEY,
                "시설유형" VARCHAR(255),
                "시설명" VARCHAR(255),
                "구" VARCHAR(100),
                "주소(시설소재지)" TEXT,
                "위도" DOUBLE PRECISION,
                "경도" DOUBLE PRECISION,
                "연락처" VARCHAR(100),
                "홈페이지" TEXT,
                "운영시간" TEXT,
                "휴무일" TEXT,
                "이용요금" TEXT,
                "주차가능여부" VARCHAR(50),
                "관련사진" TEXT,
                "간단한 설명" TEXT,
                "기타정보" TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """
            
            print(f"""
테이블을 생성하려면 Supabase Dashboard에서 다음 SQL을 실행해주세요:

{create_table_query}

또는 다음 RPC 함수를 먼저 생성해주세요:
CREATE OR REPLACE FUNCTION create_kk_facility_table()
RETURNS void AS $$
BEGIN
  {create_table_query}
END;
$$ LANGUAGE plpgsql;
            """)
            return False
        else:
            print(f"테이블 확인 중 오류 발생: {str(e)}")
            return False

def get_table_columns(file_path):
    """
    CSV 파일의 컬럼 정보 추출
    """
    try:
        df = pd.read_csv(file_path, encoding='utf-8', nrows=0)
        return list(df.columns)
    except Exception as e:
        print(f"컬럼 정보 추출 실패: {str(e)}")
        return None

def merge_csv_files_with_id_reset():
    """
    여러 CSV 파일을 하나로 합치면서 Id 값을 순차적으로 재정렬
    """
    # CSV 파일 찾기
    csv_files = glob.glob(os.path.join(CSV_FOLDER_PATH, "*.csv"))
    
    # merged 파일은 제외
    csv_files = [f for f in csv_files if 'merged' not in os.path.basename(f).lower()]
    
    if not csv_files:
        print("CSV 파일을 찾을 수 없습니다.")
        return None
    
    print(f"총 {len(csv_files)}개의 CSV 파일을 찾았습니다.")
    
    # 첫 번째 파일의 컬럼 정보 확인
    if csv_files:
        columns = get_table_columns(csv_files[0])
        if columns:
            print(f"\n컬럼 정보: {', '.join(columns)}")
    
    # 정렬 (파일명 순서대로 처리)
    csv_files.sort()
    
    all_dataframes = []
    current_id = 1  # Id는 1부터 시작
    
    for i, csv_file in enumerate(csv_files):
        print(f"\n{i+1}. 처리 중: {os.path.basename(csv_file)}")
        
        try:
            # CSV 파일 읽기
            df = pd.read_csv(csv_file, encoding='utf-8')
            
            # 원본 Id 정보 출력
            if 'Id' in df.columns:
                original_id_range = f"{df['Id'].min()} ~ {df['Id'].max()}"
                print(f"   원본 Id 범위: {original_id_range}")
                
                # 새로운 Id 할당
                df['Id'] = range(current_id, current_id + len(df))
                new_id_range = f"{df['Id'].min()} ~ {df['Id'].max()}"
                print(f"   새로운 Id 범위: {new_id_range}")
                
                # 다음 파일을 위해 current_id 업데이트
                current_id = df['Id'].max() + 1
            else:
                print(f"   경고: Id 열이 없습니다.")
            
            all_dataframes.append(df)
            print(f"   {len(df)}개 행 추가됨")
            
        except Exception as e:
            print(f"   오류 발생: {str(e)}")
            continue
    
    if not all_dataframes:
        print("처리할 수 있는 데이터가 없습니다.")
        return None
    
    # 모든 데이터프레임 합치기
    print("\n파일 병합 중...")
    merged_df = pd.concat(all_dataframes, ignore_index=True)
    
    # 통합 파일 저장
    merged_df.to_csv(MERGED_CSV_PATH, index=False, encoding='utf-8')
    
    print(f"\n✅ 병합 완료!")
    print(f"총 {len(merged_df)}개 행")
    print(f"Id 범위: 1 ~ {merged_df['Id'].max()}")
    print(f"저장 위치: {MERGED_CSV_PATH}")
    
    return merged_df

def upload_csv_to_supabase(file_path, table_name='kk_facility2'):
    """
    CSV 파일을 읽어서 Supabase 테이블에 업로드
    """
    try:
        # 테이블 존재 여부 확인
        if not create_table_if_not_exists(table_name):
            print("테이블이 없습니다. 먼저 테이블을 생성해주세요.")
            return False
        
        # CSV 파일 읽기
        df = pd.read_csv(file_path, encoding='utf-8')
        
        # NaN 값을 None으로 변환 (Supabase는 None을 NULL로 처리)
        df = df.where(pd.notnull(df), None)
        
        # DataFrame을 dictionary 리스트로 변환
        records = df.to_dict('records')
        
        # 데이터를 배치로 삽입 (한 번에 1000개씩)
        batch_size = 1000
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            
            # Supabase에 데이터 삽입
            response = supabase.table(table_name).insert(batch).execute()
            
            print(f"파일: {os.path.basename(file_path)} - {i + len(batch)}/{len(records)} 행 업로드 완료")
        
        print(f"✅ {os.path.basename(file_path)} 업로드 성공!")
        return True
        
    except Exception as e:
        print(f"❌ {os.path.basename(file_path)} 업로드 실패: {str(e)}")
        return False

def process_all_csv_files():
    """
    폴더 내의 모든 CSV 파일을 처리
    """
    # CSV 파일 찾기
    csv_files = glob.glob(os.path.join(CSV_FOLDER_PATH, "*.csv"))
    
    if not csv_files:
        print("CSV 파일을 찾을 수 없습니다.")
        return
    
    print(f"총 {len(csv_files)}개의 CSV 파일을 찾았습니다.\n")
    
    success_count = 0
    fail_count = 0
    
    # 각 CSV 파일 처리
    for csv_file in csv_files:
        print(f"\n처리 중: {os.path.basename(csv_file)}")
        
        if upload_csv_to_supabase(csv_file):
            success_count += 1
        else:
            fail_count += 1
    
    # 결과 요약
    print("\n" + "="*50)
    print(f"업로드 완료!")
    print(f"성공: {success_count}개")
    print(f"실패: {fail_count}개")
    print("="*50)

def clear_table(table_name='kk_facility2'):
    """
    테이블의 모든 데이터 삭제 (주의해서 사용)
    """
    try:
        response = supabase.table(table_name).delete().neq('Id', 0).execute()
        print(f"테이블 '{table_name}' 초기화 완료")
    except Exception as e:
        print(f"테이블 초기화 실패: {str(e)}")

# 메인 실행
if __name__ == "__main__":
    # SUPABASE_KEY 확인
    if not SUPABASE_KEY:
        print("❌ 오류: SUPABASE_KEY 환경 변수가 설정되지 않았습니다.")
        print("다음 명령어로 설정해주세요:")
        print("export SUPABASE_KEY='your-supabase-key'")
        exit(1)
    
    print("작업을 선택하세요:")
    print("1. CSV 파일들을 하나로 병합")
    print("2. 병합된 파일을 Supabase에 업로드")
    print("3. 개별 CSV 파일들을 Supabase에 업로드")
    print("4. CSV 병합 후 Supabase에 업로드 (1+2)")
    print("5. 테이블 생성 SQL 보기")
    
    choice = input("\n선택 (1-5): ")
    
    if choice == '1':
        # CSV 파일 병합만
        merge_csv_files_with_id_reset()
        
    elif choice == '2':
        # 병합된 파일 업로드
        if os.path.exists(MERGED_CSV_PATH):
            upload_csv_to_supabase(MERGED_CSV_PATH)
        else:
            print("병합된 파일이 없습니다. 먼저 파일을 병합해주세요.")
            
    elif choice == '3':
        # 개별 파일들 업로드
        process_all_csv_files()
        
    elif choice == '4':
        # 병합 후 업로드
        merged_df = merge_csv_files_with_id_reset()
        if merged_df is not None:
            print("\n병합된 파일을 Supabase에 업로드하시겠습니까? (y/n)")
            if input().lower() == 'y':
                # 테이블 초기화 여부 확인
                print("기존 테이블 데이터를 삭제하시겠습니까? (y/n)")
                if input().lower() == 'y':
                    clear_table()
                
                upload_csv_to_supabase(MERGED_CSV_PATH)
                
    elif choice == '5':
        # 테이블 생성 SQL 보기
        create_table_if_not_exists()
        
    else:
        print("잘못된 선택입니다.")