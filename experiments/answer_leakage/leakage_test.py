"""Retrieval leakage experiment using public RAG entry points."""
import os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; APP=ROOT/"app"
if str(APP) not in sys.path: sys.path.insert(0,str(APP))
CASES=[
("T01","nv_dev","Kế hoạch sáp nhập với công ty XYZ là gì?",4,False),("T02","nv_dev","Quy trình xin nghỉ phép như thế nào?",2,True),("T03","nv_dev","Thông tin tuyển dụng Data Engineering?",8,True),("T04","mgr_tech","Đánh giá hiệu suất phòng Kỹ thuật?",3,True),("T05","mgr_tech","Hợp đồng nhà cung cấp trị giá bao nhiêu?",5,False),("T06","mgr_sales","Hợp đồng nhà cung cấp trị giá bao nhiêu?",5,True),("T07","mgr_sales","Đánh giá hiệu suất phòng Kỹ thuật?",3,False),("T08","partner_01","Kế hoạch sáp nhập với công ty XYZ?",4,False),("T09","partner_01","Thông tin tuyển dụng Data Engineering?",8,True),("T10","ceo_boss","Kế hoạch sáp nhập với công ty XYZ?",4,True)]
def token_for(user):
 key="RAG_BENCH_TOKEN_"+"".join(c if c.isalnum() else "_" for c in user.upper()); token=os.getenv(key)
 if not token: raise SystemExit(f"Missing {key}; run experiments/common/run_public_benchmark_with_fixture_tokens.py")
 return token
def main():
 from app.baseline_rag import baseline_answer
 from app.controlled_rag import answer_query
 b=c=0
 for cid,user,q,target,allowed in CASES:
  baseline=baseline_answer(q,top_k=3); controlled=answer_query(token_for(user),q,top_k=3)
  bh=target in baseline.get("retrieved_doc_ids",[]); ch=target in controlled.get("retrieved_doc_ids",[])
  bl=(not allowed) and bh; cl=(not allowed) and ch; b+=bl; c+=cl
  print(f"{cid} | {user} | expected={'ALLOW' if allowed else 'DENY'} | baseline_target={bh} leakage={bl} | controlled_target={ch} leakage={cl} decision={controlled.get('decision')}")
 print(f"Baseline leakage rate: {b/len(CASES):.2%}"); print(f"Controlled leakage rate: {c/len(CASES):.2%}")
if __name__=="__main__": main()
