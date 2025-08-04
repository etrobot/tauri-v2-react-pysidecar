import pandas as pd
import time
from fluctuation import getChanges

def get_resource_path(relative_path):
    import sys, os
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def worker(concept_df, queue, interval=3, batch_interval=300, batch_size=100):
    print("[get_changes_worker_queue] 启动，推送到主进程Queue并定时批量写入磁盘")
    changes_path = get_resource_path("static/changes.csv")
    change_buffer = []
    last_write = time.time()
    while True:
        try:
            df = getChanges(concept_df)
            data = df.where(pd.notnull(df), None).to_dict(orient="records")
            queue.put(data)
            change_buffer.append(df)
        except Exception as e:
            print(f"[get_changes_worker_queue] getChanges错误: {e}")
        now = time.time()
        if len(change_buffer) >= batch_size or (now - last_write) >= batch_interval:
            if change_buffer:
                try:
                    all_df = pd.concat(change_buffer, ignore_index=True)
                    all_df.to_csv(changes_path, index=False)
                    print(f"[get_changes_worker_queue] 批量写入 {len(change_buffer)} 条变更到 {changes_path}")
                    change_buffer.clear()
                    last_write = now
                except Exception as e:
                    print(f"[get_changes_worker_queue] 批量写入失败: {e}")
        time.sleep(interval)
