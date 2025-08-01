#!/usr/bin/env python3
"""
KGRAG graph construction pipeline script
Usage: python build_graph.py --dataset [dataset_name] --input [contexts.txt path]
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from typing import List, Optional

# Set project root path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def run_command(cmd: List[str], cwd: Optional[str] = None) -> bool:
    """Execute command"""
    try:
        print(f"🔄 Executing: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}")
        if e.stderr:
            print(f"Error message: {e.stderr}")
        return False

def extract_triples(input_file: str, output_file: str) -> bool:
    """Extract triples from text"""
    print(f"📝 Extracting triples: {input_file} → {output_file}")
    
    # Dynamically modify and execute graph_construction.py
    script_content = f'''
import json
from pathlib import Path
from typing import List
from dotenv import load_dotenv
import os
import openai
import tiktoken
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from prompt.extract_graph import EXTRACTION_PROMPT

if "SSL_CERT_FILE" in os.environ:
    os.environ.pop("SSL_CERT_FILE")

# Dynamic path configuration
input_path = "{input_file}"
output_path = "{output_file}"

# Load configuration
from config import get_config
config = get_config()

MODEL_NAME = config.default_model
MAX_TOKENS = config.alt_max_tokens  # Alternative chunking settings
OVERLAP = config.alt_overlap
MAX_WORKERS = config.max_workers

load_dotenv()
OPENAI_API_KEY = config.openai_api_key

def chunk_text(text: str, max_tokens: int, overlap: int, model: str) -> List[str]:
    enc = tiktoken.encoding_for_model(model)
    tokens = enc.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = start + max_tokens
        chunk_tokens = tokens[start:end]
        chunks.append(enc.decode(chunk_tokens))
        start = end - overlap
    return chunks

def call_model(client: openai.OpenAI, model: str, chunk: str, index: int) -> dict:
    prompt_filled = EXTRACTION_PROMPT.replace("{{{{document}}}}", chunk.strip())
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {{"role": "system", "content": "You are an expert in information extraction."}},
                {{"role": "user", "content": prompt_filled}}
            ],
            temperature=0.0
        )
        return {{"index": index, "result": response.choices[0].message.content.strip()}}
    except Exception as e:
        print(f"Error processing chunk {{index}}: {{e}}")
        return {{"index": index, "result": "[]"}}

# Main execution
if not os.path.exists(input_path):
    print(f"Input file not found: {{input_path}}")
    exit(1)

with open(input_path, 'r', encoding='utf-8') as f:
    text = f.read()

chunks = chunk_text(text, MAX_TOKENS, OVERLAP, MODEL_NAME)
print(f"📊 Split into {{len(chunks)}} chunks")

client = openai.OpenAI(api_key=OPENAI_API_KEY)
results = [None] * len(chunks)
pending_indices = list(range(len(chunks)))

# Load existing results (if any)
if os.path.exists(output_path):
    with open(output_path, 'r', encoding='utf-8') as f:
        try:
            existing_results = json.load(f)
            for item in existing_results:
                if isinstance(item, dict) and "index" in item and item["index"] < len(results):
                    results[item["index"]] = item
                    if item["index"] in pending_indices:
                        pending_indices.remove(item["index"])
        except:
            pass

print(f"🔄 Processing {{len(pending_indices)}} chunks...")

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {{
        executor.submit(call_model, client, MODEL_NAME, chunks[idx], idx): idx
        for idx in pending_indices
    }}
    for future in tqdm(as_completed(futures), total=len(futures), desc="Processing chunks"):
        idx = futures[future]
        results[idx] = future.result()

        if (pending_indices.index(idx) + 1) % 10 == 0 or idx == pending_indices[-1]:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)

print(f"✅ Triple extraction completed: {{output_path}}")
'''
    
    # Create and execute temporary script file
    temp_script = "temp_extract_triples.py"
    try:
        with open(temp_script, "w", encoding="utf-8") as f:
            f.write(script_content)
        
        success = run_command(["python", temp_script])
        return success
    finally:
        if os.path.exists(temp_script):
            os.remove(temp_script)

def convert_to_gexf(json_file: str, gexf_file: str) -> bool:
    """Convert JSON to GEXF"""
    print(f"🔗 GEXF conversion: {json_file} → {gexf_file}")
    return run_command(["python", "index/json_to_gexf.py", json_file, gexf_file])

def build_faiss_index(gexf_file: str, json_file: str, index_file: str, payload_file: str) -> bool:
    """Create FAISS index"""
    print(f"🔍 Creating FAISS index: {gexf_file}")
    
    # Dynamically modify and execute edge_embedding.py
    script_content = f'''
import os
import json
import networkx as nx
import numpy as np
import faiss
from typing import List, Tuple, Dict, Set
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from openai import OpenAI
from dotenv import load_dotenv

# Dynamic path configuration
GEXF_PATH = "{gexf_file}"
INDEX_PATH = "{index_file}"
PAYLOAD_PATH = "{payload_file}"
JSON_PATH = "{json_file}"
EMBEDDING_MODEL = "text-embedding-3-small"
MAX_WORKERS = 50

load_dotenv()

if "SSL_CERT_FILE" in os.environ:
    os.environ.pop("SSL_CERT_FILE")

Edge = Tuple[str, str, str, str, str]
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("Environment variable OPENAI_API_KEY must be set.")

def build_sent2chunk(graph_json_path: str) -> Dict[str, int]:
    with open(graph_json_path, encoding="utf-8") as f:
        data = json.load(f)
    
    mapping = {{}}
    for chunk_id, chunk in enumerate(data):
        if not isinstance(chunk, dict):
            continue
        
        result_text = chunk.get("result", "")
        if not result_text:
            continue
        
        try:
            triples = json.loads(result_text)
        except (json.JSONDecodeError, TypeError):
            continue
        
        if not isinstance(triples, list):
            continue
        
        for item in triples:
            if not isinstance(item, dict):
                continue
            
            sentence = item.get("sentence")
            
            if isinstance(sentence, str):
                mapping[sentence] = chunk_id
            elif isinstance(sentence, list):
                for s in sentence:
                    if isinstance(s, str):
                        mapping[s] = chunk_id
    
    return mapping

class EdgeEmbedderFAISS:
    def __init__(self, gexf_path: str, embedding_model: str, openai_api_key: str, 
                 index_path: str, payload_path: str, json_path: str) -> None:
        self.graph = nx.read_gexf(gexf_path)
        self.embedding_model = embedding_model
        self.openai = OpenAI(api_key=openai_api_key)
        self.index_path = index_path
        self.payload_path = payload_path
        self.json_path = json_path
        
        self.edges: List[Edge] = []
        for src, dst, data in self.graph.edges(data=True):
            label = data.get("label") or data.get("relation_type", "")
            sentence_block = data.get("sentence", "")
            if sentence_block:
                sentences = [s.strip() for s in sentence_block.split("/") if s.strip()]
                for i, sentence in enumerate(sentences):
                    eid = f"{{src}}-{{dst}}-{{label}}".replace(" ", "_") + f"#{{i}}"
                    self.edges.append((eid, src, dst, label, sentence))
        
        self.index: faiss.IndexFlatIP
        self.payloads: List[Dict] = []
        self.sent2cid = build_sent2chunk(self.json_path)
    
    def _embed(self, text: str) -> np.ndarray:
        resp = self.openai.embeddings.create(input=[text], model=self.embedding_model)
        emb = np.array(resp.data[0].embedding, dtype="float32")
        return emb / np.linalg.norm(emb)
    
    def build_index(self) -> None:
        dim = self._embed("test").shape[0]
        self.index = faiss.IndexFlatIP(dim)
        
        seen: set[str] = set()
        vecs, payloads = [], []
        
        def worker(edge: Edge):
            eid, src, dst, lbl, sent = edge
            key = sent
            if key in seen:
                return None
            emb = self._embed(sent)
            cid = self.sent2cid.get(key)
            payload = {{
                "edge_id": eid,
                "source": src,
                "target": dst,
                "label": lbl,
                "sentence": sent,
                "chunk_id": cid,
            }}
            return emb, payload
        
        results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for res in tqdm(executor.map(worker, self.edges), total=len(self.edges), desc="Embedding edges"):
                if res is None:
                    continue
                emb, payload = res
                vecs.append(emb)
                payloads.append(payload)
        
        self.payloads = payloads
        self.index.add(np.vstack(vecs))
        
        faiss.write_index(self.index, self.index_path)
        np.save(self.payload_path, np.array(self.payloads, dtype=object))

# Execute
embedder = EdgeEmbedderFAISS(
    gexf_path=GEXF_PATH,
    json_path=JSON_PATH,
    embedding_model=EMBEDDING_MODEL,
    openai_api_key=OPENAI_API_KEY,
    index_path=INDEX_PATH,
    payload_path=PAYLOAD_PATH,
)

if not os.path.exists(INDEX_PATH):
    embedder.build_index()
    print("FAISS index & payloads creation completed.")
'''
    
    # Create and execute temporary script file
    temp_script = "temp_build_index.py"
    try:
        with open(temp_script, "w", encoding="utf-8") as f:
            f.write(script_content)
        
        success = run_command(["python", temp_script])
        return success
    finally:
        if os.path.exists(temp_script):
            os.remove(temp_script)

def main():
    parser = argparse.ArgumentParser(description="KGRAG 그래프 구축 파이프라인")
    parser.add_argument("--dataset", required=True, help="데이터셋 이름 (예: hotpotQA)")
    parser.add_argument("--input", help="입력 contexts.txt 파일 경로")
    parser.add_argument("--skip-extraction", action="store_true", help="트리플 추출 단계 건너뛰기")
    parser.add_argument("--skip-gexf", action="store_true", help="GEXF 변환 단계 건너뛰기")
    parser.add_argument("--skip-index", action="store_true", help="인덱스 생성 단계 건너뛰기")
    
    args = parser.parse_args()
    
    # 현재 스크립트 디렉터리와 프로젝트 루트 설정
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    os.chdir(project_root)
    
    # 환경 변수 확인
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        return False
    
    # 경로 설정
    dataset_dir = Path(args.dataset)
    dataset_dir.mkdir(exist_ok=True)
    
    input_file = args.input or str(dataset_dir / "contexts.txt")
    json_file = str(dataset_dir / "graph_v1.json")
    gexf_file = str(dataset_dir / "graph_v1.gexf")
    processed_gexf = str(dataset_dir / "graph_v1_processed.gexf")
    index_file = str(dataset_dir / "edge_index_v1.faiss")
    payload_file = str(dataset_dir / "edge_payloads_v1.npy")
    
    print(f"🚀 [{args.dataset}] 그래프 구축 시작")
    print("=" * 50)
    
    # 1. 트리플 추출
    if not args.skip_extraction:
        if not os.path.exists(input_file):
            print(f"❌ 입력 파일을 찾을 수 없습니다: {input_file}")
            return False
        
        if not extract_triples(input_file, json_file):
            print("❌ 트리플 추출 실패")
            return False
    
    # 2. GEXF 변환
    if not args.skip_gexf:
        if not os.path.exists(json_file):
            print(f"❌ JSON 파일을 찾을 수 없습니다: {json_file}")
            return False
        
        if not convert_to_gexf(json_file, gexf_file):
            print("❌ GEXF 변환 실패")
            return False
        
        # processed 파일 복사
        import shutil
        shutil.copy2(gexf_file, processed_gexf)
    
    # 3. FAISS 인덱스 생성
    if not args.skip_index:
        if not os.path.exists(processed_gexf):
            print(f"❌ GEXF 파일을 찾을 수 없습니다: {processed_gexf}")
            return False
        
        if not build_faiss_index(processed_gexf, json_file, index_file, payload_file):
            print("❌ FAISS 인덱스 생성 실패")
            return False
    
    print(f"🎉 [{args.dataset}] 그래프 구축 완료!")
    print("생성된 파일들:")
    for file_path in [json_file, gexf_file, processed_gexf, index_file, payload_file]:
        if os.path.exists(file_path):
            size = os.path.getsize(file_path)
            print(f"  ✅ {file_path} ({size:,} bytes)")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
