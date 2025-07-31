import { useEffect, useState } from "react";
import "./App.css";

function isTradingHours() {
  const now = new Date();
  // 转为北京时间
  const beijingTime = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Shanghai' }));
  const day = beijingTime.getDay(); // 0 = Sunday, 1 = Monday, ..., 6 = Saturday
  const hours = beijingTime.getHours();
  const minutes = beijingTime.getMinutes();
  const currentMinutes = hours * 60 + minutes;
  // 周一到周五，且在 9:30-11:30 或 13:00-15:00
  return (
    day >= 1 && day <= 5 &&
    ((currentMinutes >= 9 * 60 + 30 && currentMinutes < 11 * 60 + 30) ||
      (currentMinutes >= 13 * 60 && currentMinutes < 15 * 60))
  );
}

interface ChangeItem {
  [key: string]: any;
}

interface ConceptMap {
  [conceptName: string]: {
    上午: { [time: string]: string[] };
    下午: { [time: string]: string[] };
  };
}

function App() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [concepts, setConcepts] = useState<ConceptMap>({});
  const [trading, setTrading] = useState(isTradingHours());

  // 检查交易时间并定时刷新
  useEffect(() => {
    const interval = setInterval(() => {
      setTrading(isTradingHours());
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  // 加载数据
  useEffect(() => {
    if (!trading) {
      setLoading(false);
      setConcepts({});
      return;
    }
    setLoading(true);
    setError(null);
    fetch('http://0.0.0.0:61125/api/changes/json', {
      method: 'GET',
      headers: { Accept: 'application/json' },
    })
      .then((response) => {
        if (!response.ok) throw new Error('Network response was not ok');
        return response.json();
      })
      .then((json) => {
        if (json && json.length > 0) {
          // 处理分组
          const concepts: ConceptMap = {};
          json.forEach((item: ChangeItem) => {
            const conceptName = item["板块名称"];
            if (!concepts[conceptName]) {
              concepts[conceptName] = { 上午: {}, 下午: {} };
            }
            const time = item["时间"];
            const name = item["名称"];
            const roundedValue = item["四舍五入取整"];
            const type = item["类型"];

            let valueStr = roundedValue > 0 ? `+${roundedValue}` : `${roundedValue}`;
            if (type === "封涨停板") {
              valueStr = `<span class='text-red-600'>${valueStr}</span>`;
            }

            const info = `<span>${name} ${type} ${valueStr}</span>`;
            const period = item["上下午"];

            if (period === "上午" || period === "下午") {
              const periodKey = period as '上午' | '下午';
              if (!concepts[conceptName][periodKey][time]) {
                concepts[conceptName][periodKey][time] = [];
              }
              concepts[conceptName][periodKey][time].push(info);
            }
          });
          setConcepts(concepts);
          setLoading(false);
        } else {
          setLoading(false);
          setConcepts({});
        }
      })
      .catch((err) => {
        console.error('Error loading data:', err);
        setError('加载数据失败，请稍后重试');
        setLoading(false);
      });
  }, [trading]);

  useEffect(() => {
    // 添加调试信息
    const now = new Date();
    const beijingTime = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Shanghai' }));
    const day = beijingTime.getDay();
    const hours = beijingTime.getHours();
    const minutes = beijingTime.getMinutes();

    console.log('Beijing Time:', beijingTime);
    console.log('Day:', day, 'Time:', hours + ':' + minutes);
    console.log('Is trading hours:', trading);
  }, [trading]);

  return (
    <div className="bg-gray-100 p-6">
      <div className="container mx-auto bg-white rounded-lg shadow-md p-6 max-w-7xl">
        <h1 className="text-2xl font-bold text-gray-800 text-center mb-6">盘口异动</h1>
        <div className="mt-6">
          <div className="text-center py-4" id="loading" style={{display: loading ? 'block' : 'none'}}>
            {trading ? '正在更新数据...' : '当前非交易时间（交易时间：周一至周五 9:30-11:30, 13:00-15:00 北京时间）'}
          </div>
          {error && (
            <div className="text-center py-4 text-red-500">{error}</div>
          )}
          <div id="data-container" style={{display: !loading && !error && trading ? 'block' : 'none'}}>
            <table className="w-full text-xs border-collapse table-fixed">
              <thead>
                <tr className="bg-amber-100">
                  <th className="p-2 border" style={{ width: '10%' }}>板块</th>
                  <th className="p-2 border" style={{ width: '45%' }}>上午</th>
                  <th className="p-2 border" style={{ width: '45%' }}>下午</th>
                </tr>
              </thead>
              <tbody id="concepts-body" className="divide-y divide-gray-200">
                {Object.keys(concepts).length === 0 ? (
                  <tr><td colSpan={3} className="text-center py-4">暂无数据</td></tr>
                ) : (
                  Object.entries(concepts).map(([conceptName, periods]) => (
                    <tr key={conceptName}>
                      <td className="p-2 font-semibold align-top border">{conceptName}</td>
                      {["上午", "下午"].map((period) => {
                        const timeGroups = periods[period as "上午" | "下午"];
                        const sortedTimes = Object.keys(timeGroups).sort();
                        return (
                          <td key={period} className="p-2 align-top border">
                            {sortedTimes.map((time) => (
                              <p key={time} dangerouslySetInnerHTML={{ __html: `${time} ${timeGroups[time].join(", ")}` }} />
                            ))}
                          </td>
                        );
                      })}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;

