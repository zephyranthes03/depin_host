import random
import os
import re
import ast
import redis
import subprocess
import sqlite3
import json
from web3 import Web3
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Form, Query
from fastapi.responses import FileResponse
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js 클라이언트 주소
    allow_credentials=True,
    allow_methods=["*"],  # 모든 HTTP 메서드 허용
    allow_headers=["*"],   # 모든 헤더 허용
)

UPLOAD_PATH = "./uploads/"
STREAM_PATH = "./streaming/"
IPFS_GATEWAY = "https://ipfs.io/ipfs/"  # IPFS 게이트웨이 설정
ETH_RPC_URL = os.getenv("ETH_RPC_URL", "http://localhost:8545")
PRIVATEKEY = os.getenv("PRIVATEKEY")
FLAT_DIRECTORY = os.getenv("FLAT_DIRECTORY")

web3 = Web3(Web3.HTTPProvider(ETH_RPC_URL))

os.makedirs(UPLOAD_PATH, exist_ok=True)
os.makedirs(STREAM_PATH, exist_ok=True)

class FileRequest(BaseModel):
    cid: str  # Filecoin/IPFS CID
    filename: str  # file name

# Redis 및 데이터베이스 설정
redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
DB_PATH = "./streaming_logs.db"

STREAMING_SERVERS_BY_CID = "streaming_servers_by_cid"  # CID 기반 색인
STREAMING_SERVERS_BY_ADDRESS = "streaming_servers_by_addr"  # 서버 URL 기반 색인
ETHSTORAGE_CONTRACT_ADDRESS = "0x..."  # 실제 EthStorage 컨트랙트 주소 입력
cid_pattern = re.compile(r"address = (0x[a-fA-F0-9]{40})")
address_pattern = re.compile(r"FlatDirectory: Address is (0x[a-fA-F0-9]{40})")

# 데이터베이스 초기화 (기록용)
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS streaming_access_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cid TEXT,
        blockchain_address TEXT,
        creator_wallet TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.commit()

# 콘텐츠 메타데이터 테이블 생성
cursor.execute("""
    CREATE TABLE IF NOT EXISTS content_metadata (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cid TEXT UNIQUE,
        video_name TEXT,
        content_creator_wallet TEXT,
        creator_share INTEGER,
        provider_share INTEGER,
        price REAL
    )
""")
conn.commit()


# 등록 요청 데이터 모델
class StreamServer(BaseModel):
    cid: str
    stream_url: str
    video_name: str
    content_creator_wallet: str
    content_distributor_wallet: str
    creator_share: int  # 예: 70%
    provider_share: int  # 예: 30%
    price: float  

class ContentMeta(BaseModel):
    video_name: str
    content_creator_wallet: str
    creator_share: int
    provider_share: int
    price: float
    cid: str = None  # Optional, will be assigned later

class DeregisterRequest(BaseModel):
    cid: str
    content_distributor_wallet: str  # 요청자의 지갑 주소 (소유자 검증용)


# ✅ 요청 데이터 모델
class RecordViewRequest(BaseModel):
    cid: str
    blockchain_address: str
    provider_wallet: str
    creator_wallet: str
    price: str
    timestamp: str


# test URL

# curl -X POST "http://localhost:8000/upload-content" \
#      -H "Content-Type: multipart/form-data" \
#      -F "file=@./data/source1.mov" \
#      -F 'json_data={"video_name": "lobster dance", "content_creator_wallet": "0x1234", "creator_share": 70, "provider_share": 30, "price": 0.001}'



@app.post("/upload-content")
async def upload_content(
    file: UploadFile = File(...), 
    json_data: str = Form(...)
):
    """파일을 업로드 후 IPFS에 저장 및 CID 반환, SQLite에 메타데이터 저장"""
    
    # 1️⃣ JSON 데이터를 Pydantic 모델로 변환
    try:
        meta = ContentMeta(**json.loads(json_data))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    
    file_location = os.path.join(UPLOAD_PATH, file.filename)
    
    # 2️⃣ 파일 저장
    with open(file_location, "wb") as buffer:
        buffer.write(await file.read())

    # 3️⃣ IPFS를 통해 파일 업로드
    cmd = f"ipfs add -r --quieter {file_location}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail="IPFS upload failed.")

    # 4️⃣ CID 추출
    cid = result.stdout.strip()
    meta.cid = cid  # CID 저장
    
    # 5️⃣ SQLite에 메타데이터 저장
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO content_metadata (cid, video_name, content_creator_wallet, creator_share, provider_share, price)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (meta.cid, meta.video_name, meta.content_creator_wallet, meta.creator_share, meta.provider_share, meta.price))

        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="CID already exists in the database.")
    finally:
        conn.close()

    return {
        "message": "File uploaded successfully.",
        "meta": meta
    }

# curl -X POST "http://localhost:8000/upload-content-web3" \
#      -H "Content-Type: multipart/form-data" \
#      -F "file=@./data/source1.mov" \
#      -F 'json_data={"video_name": "source1.mov", "content_creator_wallet": "0xB9a3799106B0364331d4e154F5f76BFF7E62D4BC", "creator_share": 70, "provider_share": 30, "price": 0.001}'

@app.post("/upload-content-web3")
async def upload_content_web3(
    file: UploadFile = File(...), 
    json_data: str = Form(...)
):
    """파일을 업로드 후 EthStorage에 저장 및 CID 반환, SQLite에 메타데이터 저장"""
    
    # 1️⃣ JSON 데이터를 Pydantic 모델로 변환
    try:
        meta = ContentMeta(**json.loads(json_data))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    
    file_location = os.path.join(UPLOAD_PATH, file.filename)
    
    # 2️⃣ 파일 저장
    with open(file_location, "wb") as buffer:
        buffer.write(await file.read())

    # # 3️⃣ EthStorage 업로드 수행 (ethfs-uploader 활용)
    cmd = f"ethfs-cli create -p {PRIVATEKEY} -c 11155111 -r {ETH_RPC_URL} --type blob"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail="EthStorage create failed.")

    FLAT_DIRECTORY = address_pattern.search(result.stdout).group(1)

    # 3️⃣ EthStorage 업로드 수행 (ethfs-uploader 활용)
    cmd = f"ethfs-cli upload -f {file_location} -a {FLAT_DIRECTORY} -p {PRIVATEKEY} -c 11155111 -r {ETH_RPC_URL} --type blob"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail="EthStorage upload failed.")

    # 4️⃣ CID 추출
    cid = cid_pattern.search(result.stdout).group(1)

    meta.cid = cid  # CID 저장
    
    # 5️⃣ SQLite에 메타데이터 저장
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO content_metadata (cid, video_name, content_creator_wallet, creator_share, provider_share, price)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (meta.cid, meta.video_name, meta.content_creator_wallet, meta.creator_share, meta.provider_share, meta.price))

        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="CID already exists in the database.")
    finally:
        conn.close()

    return {
        "message": "File uploaded successfully to EthStorage.",
        "web3_url": f"web3://{meta.cid}",  # Web3:// URL 반환
        "meta": meta
    }
    

#
# curl -X DELETE "http://localhost:8000/delete-content_web3/QmX1hb49by46TeJZfhn2Va9UTNPfrSyGgPcPTCrvQkMfhA"

@app.delete("/delete-content_web3/{cid}")
async def delete_content_web3(cid: str):
    """EthStorage에 업로드된 파일 및 SQLite의 메타데이터 삭제"""

    # 1️⃣ SQLite에서 CID가 존재하는지 확인하고 파일명 가져오기
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT video_name FROM content_metadata WHERE cid = ?", (cid,))
    result = cursor.fetchone()

    if not result:
        conn.close()
        raise HTTPException(status_code=404, detail="CID가 존재하지 않습니다.")

    video_name = result[0]  # 조회된 파일명

    cmd = f"ethfs-cli remove -c {cid} -f {video_name} -a {PRIVATEKEY} -r {ETH_RPC_URL}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"EthStorage 파일 삭제 실패: {result.stderr}")

    # 3️⃣ SQLite에서 메타데이터 삭제
    try:
        cursor.execute("DELETE FROM content_metadata WHERE cid = ?", (cid,))
        conn.commit()
    except sqlite3.DatabaseError as e:
        raise HTTPException(status_code=500, detail=f"SQLite 삭제 오류: {str(e)}")
    finally:
        conn.close()

    return {
        "message": "파일 및 메타데이터가 성공적으로 삭제되었습니다.",
        "cid": cid,
        "file_name": video_name
    }


@app.post("/register")
def register_server(server: StreamServer):

    # redis_client.set(server.cid, server.stream_url)

    server_info = {
        "cid": server.cid,
        "video_name": server.video_name,
        "content_creator_wallet": server.content_creator_wallet,
        "content_distributor_wallet": server.content_distributor_wallet,
        "creator_share": server.creator_share,
        "provider_share": server.provider_share,
        "price": server.price,
        "stream_url": server.stream_url
    }

    # 3️⃣ CID 기반 색인 (여러 개 관리 가능)
    redis_client.sadd(f"{STREAMING_SERVERS_BY_CID}:{server.cid}", str(server_info))

    # 4️⃣ 서버 URL 기반 색인 (여러 개 관리 가능)
    # parsed_url = urlparse(stream_url)

    # 호스트 + 포트만 추출
    # base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

    redis_client.sadd(f"{STREAMING_SERVERS_BY_ADDRESS}:{server.content_distributor_wallet}:{server.cid}", str(server_info))

    return {"message": "서버 등록 및 변환 완료", "server": server_info}


@app.post("/deregister")
def deregister_server(request: DeregisterRequest):
    """ DePIN 스트리밍 서버 제거 (소유자 검증 포함) """
    
    cid_key = f"{STREAMING_SERVERS_BY_CID}:{request.cid}"
    wallet_key = f"{STREAMING_SERVERS_BY_ADDRESS}:{request.content_distributor_wallet}:{request.cid}"

    # 1️⃣ Retrieve all servers linked to the CID
    servers_by_cid = redis_client.smembers(cid_key)
    if not servers_by_cid:
        raise HTTPException(status_code=404, detail="해당 CID에 대한 스트리밍 서버를 찾을 수 없습니다.")

    # 2️⃣ Find the matching server by stream URL
    server_to_remove = None
    servers_by_wallet = redis_client.smembers(wallet_key)
    if not servers_by_wallet:
        raise HTTPException(status_code=404, detail="해당 WALLET에 대한 스트리밍 서버를 찾을 수 없습니다.")
    else:
        for server_str in servers_by_wallet:
            server_data = ast.literal_eval(server_str)
            if server_data["content_distributor_wallet"] != request.content_distributor_wallet:
                raise HTTPException(status_code=403, detail="해당 스트리밍 서버를 제거할 권한이 없습니다.")
            server_to_remove = server_str
            break

    if not server_to_remove:
        raise HTTPException(status_code=404, detail="해당 CID에 대한 특정 스트리밍 서버를 찾을 수 없습니다.")

    # 4️⃣ Remove the server from CID-based index
    redis_client.srem(cid_key, server_to_remove)

    # 5️⃣ Remove the server from URL-based index
    redis_client.srem(wallet_key, server_to_remove)

    return {
        "message": "서버 제거 완료",
        "cid": request.cid,
        "content_distributor_wallet": request.content_distributor_wallet



    }

@app.get("/get_stream_by_cid/{cid}")
def get_stream_by_cid(cid: str):
    """CID 기반으로 등록된 단일 스트리밍 서버 정보 반환"""
    cid_key = f"{STREAMING_SERVERS_BY_CID}:{cid}"
    servers = redis_client.smembers(cid_key)

    if not servers:
        raise HTTPException(status_code=404, detail="해당 CID에 대한 스트리밍 서버가 없습니다.")

    # 첫 번째 값만 선택 (집합에서 하나의 값 가져오기)
    first_server = next(iter(servers))  # set에서 첫 번째 요소 가져오기
    server_data = ast.literal_eval(first_server)  # 문자열을 딕셔너리로 변환

    return {"cid": cid, "server": server_data}

@app.get("/get_all_streams_by_cid")
def search_streams_by_partial_cid():
    """일부 CID 값이 포함된 스트리밍 서버 정보 반환"""
    
    # 패턴을 활용하여 CID 키 검색
    pattern = f"{STREAMING_SERVERS_BY_CID}*"
    matching_keys = list(redis_client.scan_iter(pattern))

    if not matching_keys:
        raise HTTPException(status_code=404, detail="해당 패턴과 일치하는 CID가 없습니다.")

    result = {}

    for key in matching_keys:
        servers = redis_client.smembers(key)
        if servers:
            # 문자열 데이터를 딕셔너리로 변환
            server_list = [ast.literal_eval(server) for server in servers]
            result[key] = server_list

    return {"matching_cids": result}

@app.get("/get_all_streams_by_uid")
def search_streams_by_partial_cid():
    """일부 CID 값이 포함된 스트리밍 서버 정보 반환"""
    
    # 패턴을 활용하여 CID 키 검색
    pattern = f"{STREAMING_SERVERS_BY_ADDRESS}*"
    matching_keys = list(redis_client.scan_iter(pattern))

    if not matching_keys:
        raise HTTPException(status_code=404, detail="해당 패턴과 일치하는 CID가 없습니다.")

    result = {}

    for key in matching_keys:
        servers = redis_client.smembers(key)
        if servers:
            # 문자열 데이터를 딕셔너리로 변환
            server_list = [ast.literal_eval(server) for server in servers]
            result[key] = server_list

    return {"matching_cids": result}


@app.get("/get_list_stream_by_wallet/{walletid}")
def get_list_stream_by_cid(walletid: str):
    """WALLET 기반으로 등록된 모든 스트리밍 서버 정보 반환"""
    pattern = f"{STREAMING_SERVERS_BY_ADDRESS}:{walletid}"
    matching_keys = list(redis_client.scan_iter(pattern))

    if not matching_keys:
        raise HTTPException(status_code=404, detail="해당 WALLET에 대한 스트리밍 서버가 없습니다.")

    result = {}

    for key in matching_keys:
        servers = redis_client.smembers(key)
        if servers:
            # 문자열 데이터를 딕셔너리로 변환
            server_list = [ast.literal_eval(server) for server in servers]
            result[key] = server_list

    return {"results": result}    


@app.get("/get_stream_by_wallet_cid/{walletid}/{cid}")
def get_list_stream_by_cid(walletid: str, cid: str):
    """WALLET 기반으로 등록된 모든 스트리밍 서버 정보 반환"""
    wallet_key = f"{STREAMING_SERVERS_BY_ADDRESS}:{walletid}:{cid}"
    servers = redis_client.smembers(wallet_key)

    if not servers:
        raise HTTPException(status_code=404, detail="해당 WALLET/CID에 대한 스트리밍 서버가 없습니다.")

    # 문자열을 딕셔너리로 변환
    server_list = [ast.literal_eval(server) for server in servers]

    return {"wallet": walletid, "servers": server_list}


@app.get("/get_list_stream_by_cid/{cid}")
def get_list_stream_by_cid(cid: str):
    """CID 기반으로 등록된 모든 스트리밍 서버 정보 반환"""
    cid_key = f"{STREAMING_SERVERS_BY_CID}:{cid}"
    servers = redis_client.smembers(cid_key)

    if not servers:
        raise HTTPException(status_code=404, detail="해당 CID에 대한 스트리밍 서버가 없습니다.")

    # 문자열을 딕셔너리로 변환
    server_list = [ast.literal_eval(server) for server in servers]

    return {"cid": cid, "servers": server_list}


@app.get("/meta/get_metadata/{cid}")
def get_metadata(cid: str):
    """CID 기반으로 메타데이터 조회"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT video_name, content_creator_wallet, creator_share, provider_share, price
        FROM content_metadata WHERE cid = ?
    """, (cid,))
    
    data = cursor.fetchone()
    conn.close()

    if not data:
        raise HTTPException(status_code=404, detail="CID에 대한 메타데이터를 찾을 수 없습니다.")

    return {
        "cid": cid,
        "video_name": data[0],
        "content_creator_wallet": data[1],
        "creator_share": data[2],
        "provider_share": data[3],
        "price": data[4]
    }

@app.get("/meta/get_all_metadata")
def get_all_metadata():
    """전체 메타데이터 조회"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT cid, video_name, content_creator_wallet, creator_share, provider_share, price
        FROM content_metadata
    """)
    
    data = cursor.fetchall()
    conn.close()

    if not data:
        raise HTTPException(status_code=404, detail="메타데이터가 존재하지 않습니다.")

    metadata_list = [
        {
            "cid": row[0],
            "video_name": row[1],
            "content_creator_wallet": row[2],
            "creator_share": row[3],
            "provider_share": row[4],
            "price": row[5]
        }
        for row in data
    ]

    return {"metadata": metadata_list}


@app.post("/api/record-view")
def record_view(req: RecordViewRequest):
    """ 스트리밍 접속 기록 저장 """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO streaming_access_logs (cid, blockchain_address, provider_wallet, creator_wallet, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (req.cid, req.blockchain_address, req.provider_wallet, req.creator_wallet, req.price, req.timestamp))

        conn.commit()
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 오류: {str(e)}")
    finally:
        conn.close()

    return {"message": "접속 기록 저장 완료", "cid": req.cid, "creator_wallet": req.creator_wallet}


@app.get("/api/get-records/cid/{cid}")
def get_records_cid(
    cid: str,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)")
):
    """ 특정 cid 및 blockchain_address에 대한 접속 기록을 기간 단위로 조회 """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        query = """
            SELECT cid, blockchain_address, provider_wallet, creator_wallet, price, timestamp
            FROM streaming_access_logs
            WHERE cid = ?
        """
        params = [cid]

        # 기간 필터링 추가
        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date + " 00:00:00")  # 날짜 기준 00:00:00부터
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date + " 23:59:59")  # 날짜 기준 23:59:59까지

        query += " ORDER BY timestamp DESC"  # 최신 데이터부터 정렬

        cursor.execute(query, tuple(params))
        records = cursor.fetchall()

        if not records:
            raise HTTPException(status_code=404, detail="No records found.")

        # 데이터 형식 변환 (리스트 형태로 반환)
        result = [
            {"cid": r[0], "blockchain_address": r[1], "provider_wallet": r[2], "creator_wallet": r[3], "price": r[4], "timestamp": r[5]}
            for r in records
        ]
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"DB 조회 오류: {str(e)}")
    finally:
        conn.close()

    return {"records": result}



@app.get("/api/get-records/provider/{provider_wallet}")
def get_records_provider(
    provider_wallet: str,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)")
):
    """ 특정 cid 및 blockchain_address에 대한 접속 기록을 기간 단위로 조회 """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        query = """
            SELECT cid, blockchain_address, provider_wallet, creator_wallet, price, timestamp
            FROM streaming_access_logs
            WHERE provider_wallet = ?
        """
        params = [provider_wallet]

        # 기간 필터링 추가
        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date + " 00:00:00")  # 날짜 기준 00:00:00부터
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date + " 23:59:59")  # 날짜 기준 23:59:59까지

        query += " ORDER BY timestamp DESC"  # 최신 데이터부터 정렬

        cursor.execute(query, tuple(params))
        records = cursor.fetchall()

        if not records:
            raise HTTPException(status_code=404, detail="No records found.")

        # 데이터 형식 변환 (리스트 형태로 반환)
        result = [
            {"cid": r[0], "blockchain_address": r[1], "provider_wallet": r[2], "creator_wallet": r[3], "price": r[4], "timestamp": r[5]}
            for r in records
        ]
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"DB 조회 오류: {str(e)}")
    finally:
        conn.close()

    return {"records": result}

