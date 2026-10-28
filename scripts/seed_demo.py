"""Create an idempotent text demonstration through the public HTTP API."""
import argparse
import httpx
DEMO = ['张三参与语音项目。','他属于星河公司。','语音项目依赖离线方案。','那个方案导致成本下降。','另外说，知识图谱属于人工智能。','图谱检索依赖知识图谱。','明天李四参与图谱检索。','语音项目可能依赖云端服务，仍待确认。']

def main() -> None:
    """Seed a labeled demo session, then print its workspace URL."""
    parser=argparse.ArgumentParser(); parser.add_argument('--api',default='http://127.0.0.1:8000'); args=parser.parse_args()
    with httpx.Client(base_url=args.api,timeout=180,trust_env=False) as client:
        response=client.get('/api/sessions'); response.raise_for_status()
        old=next((s for s in response.json() if s['title']=='演示 · 声音如何变成知识'),None)
        if old and old['status']=='ready':
            print(f"http://localhost:3000/sessions/{old['id']}"); return
        response=client.post('/api/sessions',json={'title':'演示 · 声音如何变成知识'}); response.raise_for_status(); sid=response.json()['id']
        response=client.put(f'/api/sessions/{sid}/transcript',json={'segments':[{'text':t,'start_ms':i*5000,'end_ms':(i+1)*5000} for i,t in enumerate(DEMO)]}); response.raise_for_status()
        response=client.post(f'/api/sessions/{sid}/process'); response.raise_for_status()
        print(f'http://localhost:3000/sessions/{sid}')
if __name__=='__main__':
    main()
