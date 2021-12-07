import numpy as np
import yfinance as yf
import pandas as pd
import statsmodels.api as sm
import os
import bs4 as bs
import requests
import random


def add_stocks_from_tickers(tickers: list[str], **kwargs: dict[str, str]) -> pd.DataFrame:
    """ Takes a stock ticker string, calculates the returns, and inserts them into a data frame

    #fetching-data-for-multiple-tickers to see how they work.
    Takes optional period and interval keyword args. Go to https://github.com/ranaroussi/yfinance
    """
    # close_prices = yf.download(tickers, period=kwargs.get('period', "10y"), interval=kwargs.get(
    #     'interval', "1d"))[['Close']].dropna()

    close_prices = yf.download(tickers, start="2014-12-01", end="2021-12-01", interval=kwargs.get(
        'interval', "1d"))[['Close']].dropna()

    close_prices.to_csv('price_downloads.csv')

    return close_prices.apply(lambda ticker: get_returns(ticker))


def get_returns(close_prices: pd.DataFrame) -> pd.DataFrame:
    """Takes a datafrom of closing prices, calculates the returns, and returns them as a dataframe"""
    offset_close = close_prices.shift(-1)
    offset_returns = offset_close / close_prices - 1
    return offset_returns.shift(1).dropna()


def add_factors_from_tickers(factors: list[str], **kwargs: dict[str, str]):
    """Takes a factor name (for better printing), a ticker representing a factor (such as a thematic index ticker) and the same kwargs as the constructor"""
    return add_stocks_from_tickers(factors, **kwargs)


def regress_factors(stocks_df: pd.DataFrame, factors_df: pd.DataFrame):
    """Takes a list of factors that you want to regress on and will print a summary of a multiple regression on those factors with the objects stock

    Can pass in self.factor_names to regress on all factors
    """
    SIGNIF_LEVEL = 0.05
    R2THRESHOLD = 0.65

    portfolios = dict()
    for stock in stocks_df:
        single_stock_df = stocks_df[stock]
        pvals_under_sig = False
        temp_factor_df: pd.DataFrame = factors_df
    
        while(not(pvals_under_sig) and (len(temp_factor_df.columns)>0)):

            ticker = stock[1] if isinstance(stock, tuple) else stock
            model = sm.OLS(single_stock_df, temp_factor_df)
            results = model.fit()
            # print(results.summary())

            factor_pvals = zip(results.pvalues.index, results.pvalues.values)
            all_pvals_under = True
            for factor_pval in factor_pvals:
                factor, pvalue = factor_pval
                if pvalue > SIGNIF_LEVEL:
                    all_pvals_under = False
                    temp_factor_df = temp_factor_df.drop(columns=factor, axis = 1)

            if(all_pvals_under):
                pvals_under_sig = True

        if(results.rsquared_adj >= R2THRESHOLD):
            print(results.summary())
        
        # for factor_pval in factor_pvals:
        #     factor, pvalue = factor_pval
        #     if pvalue < SIGNIF_LEVEL:
        #         if (portfolios.get(str(factor))) is None:
        #             portfolios[str(factor)] = set([ticker])
        #         else:
        #             portfolios[str(factor)].add(ticker)

    return portfolios




def debug_shape(dfs: list[pd.DataFrame]):
    for df in dfs:
        print(df.shape)


def add_factors_from_csv(directory) -> pd.DataFrame:
    """Takes a factor name and a CSV file, calculates the returns and returns them as a dataframe

    The first two elements should be a date column heading and a "Close" (case sensitive) column heading. The data should be two columns corresponding to dates and closing prices. 
    This method is untested and may need to be modified.
    """
    factorlist: pd.DataFrame = []
    for file in os.listdir(directory):
        filepath = directory + file
        factor_close = pd.read_csv(filepath, index_col=0, parse_dates=['Date'])

        factorlist.append(factor_close)

    combined_factors: pd.DataFrame = factorlist[0]
    for i in range(1, len(factorlist)):
        df = factorlist[i]
        combined_factors = combined_factors.join(df, on='Date', how='left', lsuffix='_left', rsuffix='_right')

    return combined_factors.apply(lambda factor: get_returns(factor))


def normalizeFactorDates(dates: pd.DataFrame, stock_factors: pd.DataFrame) -> pd.DataFrame:
    return dates.join(stock_factors, on='Date', how='left', lsuffix='_left', rsuffix='_right')


# Retrieving a list of all of the stocks in the S&P 500 index and putting them in a list
def save_sp500_tickers():
    resp = requests.get('http://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
    soup = bs.BeautifulSoup(resp.text, 'lxml')
    table = soup.find('table', {'class': 'wikitable sortable'})
    tickers = []
    for row in table.findAll('tr')[1:]:
        ticker = row.findAll('td')[0].text
        ticker = ticker.replace('\n', '')
        tickers.append(ticker)    

    
    return tickers

def get_n_random_stocks(num):

    randlist = []
    numStocksToAnalyze =num
    i = 0
    while (i < numStocksToAnalyze):
        r = random.randint(0,499)
        if r not in randlist:
            randlist.append(r) 
            i+=1
    
    stock_list = save_sp500_tickers()
    stocks_to_analyze = []
    for i in randlist:
        stocks_to_analyze.append(stock_list[i])
    
    return stocks_to_analyze
    


kwargs = {'interval': '1mo'}

#temp stock data frame so we can join our factor data with the stock data efficiently. This data frame is not processed.
tempStock = add_stocks_from_tickers(['MSFT'])
stocks_to_analyze = get_n_random_stocks(25)

stocks = add_stocks_from_tickers(stocks_to_analyze)
factors = add_factors_from_csv('factorDirectory/')

normalizedFactors = normalizeFactorDates(tempStock, factors)

for column in normalizedFactors.columns: 
    if column == 'Close':
        normalizedFactors = normalizedFactors.drop(columns=column, axis = 1)

# debug_shape([normalizedFactors,tempStock])
debug_shape([normalizedFactors, stocks])

# portfolios = regress_factors(stocks, normalizedFactors)
# print(portfolios)

