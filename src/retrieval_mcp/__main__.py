import argparse
import logging
import os
from dotenv import load_dotenv
import uvicorn

def main():
    parser = argparse.ArgumentParser(description='Run the independent retrieval service')
    parser.add_argument('--env-file', default='.env')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8050)
    args = parser.parse_args()
    load_dotenv(args.env_file, override=False)
    for key in ['HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE']:
        os.environ.setdefault(key,'1')
    for key in ['OMP_NUM_THREADS','MKL_NUM_THREADS']:
        os.environ.setdefault(key,'4')
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(name)s %(message)s')
    uvicorn.run('retrieval_mcp.api:create_app',factory=True,host=args.host,port=args.port)

if __name__ == '__main__':
    main()
