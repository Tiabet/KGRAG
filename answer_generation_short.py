import json
from graph_based_rag_short import GraphRAG
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import tiktoken

enc = tiktoken.encoding_for_model("gpt-4o")

# 입력/출력 경로
input_path = "hotpotQA/qa.json"
output_path = "Result/Ours/hotpot_30_5.json"
chunk_log_path = "Result/Ours/Chunks/used_chunks_1000_multihop.jsonl"
temp_output_path = output_path.replace(".json", "_temp.json")
MAX_WORKERS = 30  # 병렬 처리 스레드 수
TOP_K1 = 30
TOP_K2 = 5

# (1) 결과 디렉터리 없으면 만들기 ─ 가장 먼저!
os.makedirs(os.path.dirname(output_path), exist_ok=True)

# GraphRAG 인스턴스
rag = GraphRAG()

chunk_log_file = open(chunk_log_path, "w", encoding="utf-8")

# 입력 로딩
with open(input_path, 'r', encoding='utf-8') as f:
    questions = json.load(f)

# 결과 저장 리스트 (index 순서 보존)
output_data = [None] * len(questions)

# 작업 함수
def process(index_query):
    idx, item = index_query
    query = item.get("query", "")
    try:
        answer, spent, context_token = rag.answer(query=query, top_k1=TOP_K1, top_k2=TOP_K2)
        chunk_ids = rag.last_chunk_ids  # GraphRAG에서 마지막 chunk ID 기록하도록 추가 필요
    except Exception as e:
        answer = f"[Error] {e}"
        spent = 0.0
        context_token = None
        chunk_ids = []

    # 기록
    for cid in chunk_ids:
        log_entry = {"query": query, "chunk_id": cid}
        chunk_log_file.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    result = {
        "query": query,
        "result": answer,
        "time": spent,
        "context_token": context_token,
    }
    # 문장 단위로 쓰인 모든 chunk-id들 저장
    sentence_chunk_ids = set(getattr(rag, "all_sentence_chunk_ids", []))
    for cid in sentence_chunk_ids:
        log_entry = {"query": query, "sentence_chunk_id": cid}
        chunk_log_file.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    return idx, result


# 병렬 처리
completed = 0
save_every = 10

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = [executor.submit(process, (i, item)) for i, item in enumerate(questions)]
    for future in tqdm(as_completed(futures), total=len(futures), desc="Generating answers"):
        idx, result = future.result()
        output_data[idx] = result  # 순서 유지
        completed += 1

        # 10개마다 임시 저장
        if completed % save_every == 0:
            with open(temp_output_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            # print(f"[Temp Save] {completed} items saved to {temp_output_path}")

chunk_log_file.close()

# 최종 저장
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(output_data, f, indent=2, ensure_ascii=False)

print(f"Saved final output to {output_path}")

# 평균 소요 시간 및 토큰 수 계산
valid_items = [it for it in output_data if it and not it["result"].startswith("[Error]")]

if valid_items:
    avg_time   = sum(it["time"]        for it in valid_items) / len(valid_items)
    avg_tokens = sum(len(enc.encode(it["context_token"])) for it in valid_items) / len(valid_items)

    print(f"\n📊 평균 소요 시간: {avg_time:.2f}초")
    print(f"📊 평균 컨텍스트 토큰 수: {avg_tokens:.1f}개")
else:
    print("⚠️  평균 계산을 위한 유효한 결과가 없습니다.")

