import time as t
import pandas as pd
import akshare as ak
from typing import List, List

def getConcepts() -> None:
    """
    Fetch concept stock data and save to a CSV file.
    
    This function retrieves stock concepts and their constituent stocks from akshare,
    filters them by market cap, and saves the results to 'static/concepts.csv'.
    """
    concepts: List[List[str]] = [['板块代码', '板块名称', '股票代码', '股票名称']]
    stock_board_concept_name_em_df = ak.stock_board_concept_name_em()
    stock_board_concept_name_em_df.sort_values(by='总市值', ascending=True, inplace=True)
    
    for _, v in stock_board_concept_name_em_df.iterrows():
        if int(v['总市值']) > 30000000000000 or '昨日' in v['板块名称']:
            continue
            
        stock_board_concept_spot_em_df = ak.stock_board_concept_cons_em(symbol=v['板块代码'])
        for _, v2 in stock_board_concept_spot_em_df.iterrows():
            row = [v['板块代码'], v['板块名称'], v2['代码'], v2['名称']]
            concepts.append(row)
            
        print(v['板块名称'], len(concepts))
        if len(concepts) % 20 == 0:
            t.sleep(15)
            
    df = pd.DataFrame(concepts, columns=['板块代码', '板块名称', '股票代码', '股票名称'])
    df.to_csv('static/concepts.csv', index=False)
