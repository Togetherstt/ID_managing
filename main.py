from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import sqlite3
from datetime import datetime
import pandas as pd
import io
import urllib.parse
from fastapi.responses import StreamingResponse, FileResponse

app = FastAPI(title="学生节兑奖核销系统 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def init_db():
    conn = sqlite3.connect('festival.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS claims (
            student_id TEXT,
            claim_type TEXT,
            claim_time DATETIME,
            PRIMARY KEY (student_id, claim_type)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ================= 核心业务：前台核销 =================
class ClaimRequest(BaseModel):
    student_id: str
    claim_type: str

@app.post("/api/claim")
async def process_claim(request: ClaimRequest):
    student_id = request.student_id.strip()
    claim_type = request.claim_type.strip()

    if not student_id:
        return {"status": "error", "message": "学号不能为空"}
    
    try:
        conn = sqlite3.connect('festival.db')
        c = conn.cursor()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO claims (student_id, claim_type, claim_time) VALUES (?, ?, ?)", 
                  (student_id, claim_type, current_time))
        conn.commit()
        conn.close()
        return {"status": "success", "message": f"✅ 核销成功！\n学号：{student_id}\n类型：{claim_type}"}
    except sqlite3.IntegrityError:
        c.execute("SELECT claim_time FROM claims WHERE student_id=? AND claim_type=?", (student_id, claim_type))
        previous_time = c.fetchone()[0]
        conn.close()
        return {"status": "duplicate", "message": f"🚨 警报：重复领奖！\n该同学已于 {previous_time} 领取过【{claim_type}】"}

# ================= 管理员后台模块 =================
# 预设管理员密码（你可以自行修改）
ADMIN_PASSWORD = "1"

def verify_password(password: str):
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="管理员密码错误！")

@app.get("/api/admin/stats")
async def get_admin_stats(password: str = ""):
    """获取实时核销统计数据"""
    verify_password(password)
    
    conn = sqlite3.connect('festival.db')
    c = conn.cursor()
    
    # 获取各类型总计
    c.execute("SELECT claim_type, COUNT(*) FROM claims GROUP BY claim_type")
    counts = dict(c.fetchall())
    
    # 获取最新 10 条流水
    c.execute("SELECT student_id, claim_type, claim_time FROM claims ORDER BY claim_time DESC LIMIT 10")
    recent_logs = [{"student_id": row[0], "claim_type": row[1], "time": row[2]} for row in c.fetchall()]
    conn.close()
    
    return {"status": "success", "counts": counts, "recent_logs": recent_logs}

@app.get("/api/admin/export")
async def export_excel(password: str = ""):
    """一键导出 Excel 数据流"""
    verify_password(password)
    
    conn = sqlite3.connect('festival.db')
    df = pd.read_sql_query("SELECT student_id AS 学号, claim_type AS 兑奖类型, claim_time AS 核销时间 FROM claims ORDER BY claim_time DESC", conn)
    conn.close()
    
    # 在内存中生成 Excel
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='路演兑奖明细', index=False)
    buffer.seek(0)
    
    # 动态生成文件名
    file_time = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"学生节核销数据_{file_time}.xlsx"
    
    # 💡 核心修复点：将中文文件名进行 URL 编码
    encoded_filename = urllib.parse.quote(filename)
    
    # 返回二进制文件流，触发浏览器下载
    return StreamingResponse(
        buffer, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        # 💡 核心修复点：使用 filename*=utf-8'' 的标准格式来处理中文
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}"}
    )

# ================= 网页路由 =================
@app.get("/")
async def serve_front_page():
    """返回前台核销网页"""
    return FileResponse("index.html")

@app.get("/admin")
async def serve_admin_page():
    """返回后台管理网页"""
    return FileResponse("admin.html")

@app.delete("/api/admin/clear")
async def clear_all_data(password: str = ""):
    """清空所有核销记录（危险操作）"""
    verify_password(password)
    
    conn = sqlite3.connect('festival.db')
    c = conn.cursor()
    # 执行清空表的命令
    c.execute("DELETE FROM claims")
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": "所有核销记录已成功清空！"}