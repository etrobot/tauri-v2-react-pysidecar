import React, { useState, useEffect } from 'react';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import MultiSelect from './components/MultiSelect';

interface StockInfo {
  name: string;
  value: string;
  isLimit: boolean;
}

type TimeGroup = Record<string, StockInfo[]>;

interface PeriodData {
  "上午": TimeGroup;
  "下午": TimeGroup;
}

type ConceptData = Record<string, PeriodData>;

interface StockDataItem {
  "板块名称": string;
  "时间": string;
  "名称": string;
  "四舍五入取整": number;
  "类型": string;
  "上下午": "上午" | "下午";
}

const StockMarketMonitor = () => {
  const [data, setData] = useState<ConceptData>({});
  const [conceptNames, setConceptNames] = useState<string[]>([]);
  const [loadingMessage, setLoadingMessage] = useState('Loading data...');
  const [hasData, setHasData] = useState(false);
  const [updateTime, setUpdateTime] = useState<string>('');
  // 板块多选筛选
  const [selectedConcepts, setSelectedConcepts] = useState<string[]>([]);
  const isTradingHours = () => {
    const now = new Date();
    const beijingTime = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Shanghai' }));
    const day = beijingTime.getDay(); // 0 = Sunday, 1 = Monday, ..., 6 = Saturday
    const hours = beijingTime.getHours();
    const minutes = beijingTime.getMinutes();
    const currentMinutes = hours * 60 + minutes;

    // 添加调试信息
    console.log('Beijing Time:', beijingTime);
    console.log('Day:', day, 'Time:', hours + ':' + minutes);

    // Check if it's a weekday (1-5) and within market hours
    const isTrading = day >= 1 && day <= 5 && // Monday to Friday
      ((currentMinutes >= 9 * 60 + 30 && currentMinutes < 11 * 60 + 30) || // 9:30-11:30
        (currentMinutes >= 13 * 60 && currentMinutes < 15 * 60)); // 13:00-15:00

    console.log('Is trading hours:', isTrading);
    return isTrading;
  };

  // Function to load and display data
  const loadData = async () => {
    // 如果已经有数据且是交易时间，则不加载新数据
    if (hasData && !isTradingHours()) {
      return;
    }

    try {
      const response = await fetch('http://localhost:61125/api/changes/json', {
        method: 'GET',
        headers: {
          'Accept': 'application/json'
        }
      });

      if (!response.ok) throw new Error('Network response was not ok');

      const fetchedData: StockDataItem[] = await response.json();

      if (fetchedData && fetchedData.length > 0) {
        const concepts: ConceptData = {};
        const conceptNameSet = new Set<string>();
        setUpdateTime(new Date().toLocaleString('zh-CN', { hour12: false }));
        for (const item of fetchedData) {
          // 初始化概念数据
          if (!concepts[item["板块名称"]]) {
            concepts[item["板块名称"]] = { "上午": {}, "下午": {} };
          }

          const period = item["上下午"];
          const time = item["时间"];

          // 确保时间段和时间点都存在
          if (!concepts[item["板块名称"]][period][time]) {
            concepts[item["板块名称"]][period][time] = [];
          }

          // 处理数据转换
          const valueStr = item["四舍五入取整"] > 0 ?
            `+${item["四舍五入取整"]}` :
            item["四舍五入取整"].toString();

          // 添加股票信息
          concepts[item["板块名称"]][period][time].push({
            name: item["名称"],
            value: valueStr,
            isLimit: item["类型"] === "封涨停板"
          });

          // 收集板块名
          if (item["板块名称"]) {
            conceptNameSet.add(item["板块名称"]);
          }
        }
        setHasData(true);
        setData(concepts);
        setConceptNames(Array.from(conceptNameSet));
        console.log('[DEBUG] conceptNameSet', conceptNameSet, 'conceptNames', Array.from(conceptNameSet));
      }
    } catch (error) {
      console.error('Error loading data:', error);
      if (!hasData) {
        setLoadingMessage('启动服务中，请稍后...');
      }
    }
  };

  const checkAndLoadData = () => {
    // 如果还没有数据，则发送请求获取数据
    if (!hasData) {
      setLoadingMessage('正在更新数据...');
      loadData();
      return;
    }

    // 如果已经有数据，则检查是否为交易时间，如果是则不加载数据
    if (hasData && !isTradingHours()) {
      console.log('Already has data and is trading hours, skipping data load');
      return;
    }
  };

  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;
    let timeout: NodeJS.Timeout | null = null;

    // 定义一个函数，轮询时机只在交易时间或还没数据时
    const poll = () => {
      // 如果有数据且非交易时间，停止轮询，等待下一个交易时段
      if (hasData && !isTradingHours()) {
        if (interval) clearInterval(interval);
        interval = null;
        // 计算距离下一个交易时段的毫秒数
        const now = new Date();
        const beijingTime = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Shanghai' }));
        const day = beijingTime.getDay();
        const hours = beijingTime.getHours();
        const minutes = beijingTime.getMinutes();
        let msToNext = 0;
        // 只考虑工作日的下一个交易时段
        if (day >= 1 && day <= 5) {
          if (hours < 9 || (hours === 9 && minutes < 30)) {
            // 距离上午开盘
            msToNext = ((9 * 60 + 30) - (hours * 60 + minutes)) * 60 * 1000 - beijingTime.getSeconds() * 1000 - beijingTime.getMilliseconds();
          } else if (hours < 13) {
            // 距离下午开盘
            msToNext = ((13 * 60) - (hours * 60 + minutes)) * 60 * 1000 - beijingTime.getSeconds() * 1000 - beijingTime.getMilliseconds();
          } else {
            // 距离明天上午开盘
            msToNext = ((24 - hours + 9) * 60 + 30 - minutes) * 60 * 1000 - beijingTime.getSeconds() * 1000 - beijingTime.getMilliseconds();
            if (day === 5) {
              // 如果今天是周五，下次交易是下周一
              msToNext += 2 * 24 * 60 * 60 * 1000;
            }
          }
        } else {
          // 周末，距离下周一上午开盘
          const daysToMonday = ((8 - day) % 7);
          msToNext = (daysToMonday * 24 * 60 + (9 * 60 + 30) - (hours * 60 + minutes)) * 60 * 1000 - beijingTime.getSeconds() * 1000 - beijingTime.getMilliseconds();
        }
        // 设置定时器，到下一个交易时段自动恢复轮询
        timeout = setTimeout(() => {
          checkAndLoadData();
          if (!interval) {
            interval = setInterval(poll, 2000);
          }
        }, msToNext > 0 ? msToNext : 60 * 1000); // 兜底一分钟
        return;
      }
      // 正常轮询
      checkAndLoadData();
    };

    // 立即执行一次
    poll();
    if (!interval) {
      interval = setInterval(poll, 2000);
    }

    return () => {
      if (interval) clearInterval(interval);
      if (timeout) clearTimeout(timeout);
    };
  }, [hasData]);

  const renderStockInfo = (stocks: StockInfo[]): JSX.Element => {
    return (
      <>
        {stocks.map((stock, index) => (
          <React.Fragment key={index}>
            {index > 0 && ', '}
            {stock.name} {(
              stock.isLimit || Math.round(Number(stock.value)) >= 10
            ) ? (
              <span className="text-red-600 font-medium">{stock.value}</span>
            ) : (
              <span className="font-medium">{stock.value}</span>
            )}
          </React.Fragment>
        ))}
      </>
    );
  };

  const renderPeriodContent = (conceptName: string, period: "上午" | "下午"): JSX.Element[] => {
    const timeGroups = data[conceptName]?.[period] || {};
    const sortedTimes = Object.keys(timeGroups).sort();

    return sortedTimes.map((time, timeIndex) => (
      <div key={timeIndex} className="mb-1 last:mb-0">
        <span className="text-gray-600 text-xs">{time}</span>{' '}
        <span className="text-xs">{renderStockInfo(timeGroups[time])}</span>
      </div>
    ));
  };

  return (
    <div className='min-h-screen bg-gray-50'>
      <div className="mx-auto max-w-7xl p-4">
        <div className="items-center justify-between flex font-bold text-gray-800 mb-4">
          <MultiSelect
                label="板块筛选"
                options={Array.isArray(conceptNames) ? conceptNames.filter((name): name is string => typeof name === 'string').map((name) => ({ label: name, value: name })) : []}
                value={selectedConcepts}
                onChange={setSelectedConcepts}
                placeholder="请选择板块"
              />
              <h1 className="text-xl">盘口异动</h1> 
              <span className="text-xs">更新时间：{updateTime}</span>
        </div>
        {!hasData && (
          <div className="rounded-md bg-blue-50 p-4">
            <div className="text-center py-2">
              {loadingMessage}
            </div>
          </div>
        )}
        {hasData && (
          <>
            <div className="relative w-full max-h-[80vh] overflow-auto rounded-lg border border-gray-200 shadow-sm">
              <Table className="border-collapse w-full bg-white">
                <TableHeader className="sticky top-0 z-10 bg-amber-50 shadow-md">
                  <TableRow className="hover:bg-amber-50">
                    <TableHead className="w-[10%] text-left font-semibold text-gray-700">
                      板块
                    </TableHead>
                    <TableHead className="w-[45%] text-left font-semibold text-gray-700">
                      上午
                    </TableHead>
                    <TableHead className="w-[45%] text-left font-semibold text-gray-700">
                      下午
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(selectedConcepts.length ? selectedConcepts : Object.keys(data)).map((conceptName, index) => (
                    data[conceptName] && (
                      <TableRow key={index} className="hover:bg-gray-50">
                        <TableCell className="font-semibold align-top text-gray-800 border-r">
                          {conceptName}
                        </TableCell>
                        <TableCell className="align-top border-r p-3 text-left">
                          {renderPeriodContent(conceptName, "上午")}
                        </TableCell>
                        <TableCell className="align-top p-3 text-left">
                          {renderPeriodContent(conceptName, "下午")}
                        </TableCell>
                      </TableRow>
                    )
                  ))}
                </TableBody>
              </Table>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default StockMarketMonitor;