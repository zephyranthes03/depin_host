import pytest
from fastapi.testclient import TestClient
from gateway import app  # ✅ FastAPI 앱을 가져옴

client = TestClient(app)

# 테스트용 메타데이터 클래스
test_meta = {
    "video_name": "./test.mkv",
    "content_creator_wallet": "0x1234",
    "creator_share": 70,
    "provider_share": 30,
    "price": 10.0
}

def test_upload_content():
    """파일 업로드 및 IPFS CID 반환 테스트"""
    
    with open("./test.mkv", "rb") as f:
        response = client.post("/upload-content", files={"file": f}, json=test_meta)
    
    assert response.status_code == 200
    assert "cid" in response.json()

def test_register_server():
    """스트리밍 서버 등록 및 HLS 변환 테스트"""
    server_data = {
        "server_url": "http://localhost:8000",
        "video_name": "test_video.mp4",
        "content_creator_wallet": "0x1234",
        "content_distributor_wallet": "0x5678",
        "creator_share": 70,
        "provider_share": 30,
        "price": 10.0,
        "cid": "QmTestCid"
    }
    
    response = client.post("/register", json=server_data)
    
    assert response.status_code == 200
    assert response.json()["message"] == "서버 등록 및 변환 완료"
