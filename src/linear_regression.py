import numpy as np
import yfinance as yf
import pandas as pd
import statsmodels.api as sm
import matplotlib.pyplot as plt
import os
import bs4 as bs
import requests
import random
import datetime


def add_stock_from_tickers(tickers, **kwargs):
    """
    Takes a stock ticker string, calculates the returns, and inserts them into a data frame.
    Takes optional period and interval keyword args. 
    Go to https://github.com/ranaroussi/yfinance#fetching-data-for-multiple-tickers to see how they work.
    """
    if 'start' not in kwargs:
        kwargs['start'] = (datetime.datetime.today() - datetime.timedelta(days=365*5)).strftime("%Y-%m-%d")
    
    if 'end' not in kwargs: 
        kwargs['end'] = datetime.datetime.today().strftime("%Y-%m-%d")

    joint_stock_df = pd.DataFrame()
    for ticker in tickers:
        close_prices = yf.download(ticker, kwargs['start'], kwargs['end'], interval=kwargs.get(
            'interval', "1d"))[['Close']].dropna()
        try:
            close_prices = close_prices.rename(columns={'Close': f'{ticker}'})
            if joint_stock_df.empty:
                joint_stock_df = close_prices
            else:
                if(not(close_prices.empty)):
                    joint_stock_df = joint_stock_df.join(
                        close_prices, on='Date', how='left', lsuffix='_left', rsuffix='_right')
        except KeyError:
            print(f'Could not add {ticker}')

    return joint_stock_df.apply(lambda ticker: get_returns(ticker))


def get_returns(close_prices: pd.DataFrame):
    """Takes a dataframe of closing prices, calculates the returns, and returns them as a dataframe"""
    offset_close = close_prices.shift(-1)
    offset_returns = offset_close / close_prices - 1
    return offset_returns.shift(1).dropna()

def add_factors_from_tickers(factors, **kwargs):
    """Takes a factor name (for better printing), a ticker representing a factor (such as a thematic index ticker) and the same kwargs as the constructor"""
    return add_stock_from_tickers(factors, **kwargs)

def split_data(df, ratio=0.7):
    return df.iloc[:int(ratio*len(df))], df.iloc[int(ratio*len(df)):]


def test_model(model: sm.OLS, factor_test_df: pd.DataFrame, stock_test_df: pd.Series, plot=False, debug=False) -> tuple[pd.DataFrame, float]:
    """ Function calculates the series of predictions with the calculated model, then joins the series to the stock's dataframe and calculates the squared error
    """
    prediction: pd.Series = model.predict(factor_test_df)

    prediction_and_actual = prediction.to_frame('Prediction').join(
        stock_test_df, on='Date', how='left', lsuffix='_left', rsuffix='_right')

    prediction_and_actual['squared_error'] = (
        prediction_and_actual[stock_test_df.name] - prediction_and_actual['Prediction']) ** 2

    if debug:
        print(prediction_and_actual)

    mse = prediction_and_actual['squared_error'].sum() / prediction.size

    if plot:
        prediction_and_actual.plot()
        plt.show()

    return (prediction_and_actual, mse)


def test_regularized_model(model: sm.OLS, test_alpha, stock_test_df: pd.DataFrame, factor_test_df: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """We can check a stock's alpha response change by just changing the test alpha passed in.
    Function makes a regularized model with a ridge method (minimization of summation is squared errors)
    """

    reg_results = model.fit_regularized(
        method='elastic_net', alpha=test_alpha, L1_wt=0)
    prediction_df, new_mse = test_model(
        reg_results, factor_test_df, stock_test_df)
    print(f"Final alpha value used: {test_alpha}")

    return (prediction_df, new_mse)


def add_to_output_files(ticker, df_to_append: pd.DataFrame, regularization_check=False):
    """"Takes in the prediction data frame to append as a tab to an excel file. If the file does not exist, it creates it. 
    Creates different files for regularized linear regression results and basic regression results
    """

    if regularization_check:
        filename = '../output/regularized_prediction_output.xlsx'
    else:
        filename = '../output/prediction_output.xlsx'

    if(os.path.isfile(filename)):
        with pd.ExcelWriter(filename, mode='w') as writer:
            df_to_append.to_excel(writer, sheet_name=f'{ticker}')
    else:
        df_to_append.to_excel(filename, sheet_name=f'{ticker}')


def regress_factors(stocks_df: pd.DataFrame, factors_df: pd.DataFrame, signif_level=0.05, r2_threshold=0.5, outputToExcel=True):
    """Takes a list of factors that you want to regress on and will print a summary of a multiple regression on those factors with the objects stock
    Can pass in self.factor_names to regress on all factors
    """
    factors_df = sm.add_constant(factors_df)
    factor_train_df, factor_test_df = split_data(factors_df)

    portfolios = dict()
    for stock in stocks_df:
        stock_train_df, stock_test_df = split_data(stocks_df[stock])
        pvals_under_sig = False
        temp_factor_df: pd.DataFrame = factor_train_df

        while(not(pvals_under_sig) and (len(temp_factor_df.columns) > 0)):

            ticker = stock[1] if isinstance(stock, tuple) else stock
            model = sm.OLS(stock_train_df, temp_factor_df)
            results = model.fit()

            factor_pvals = zip(results.pvalues.index, results.pvalues.values)
            all_pvals_under = True

            for factor_pval in factor_pvals:
                factor, pvalue = factor_pval
                if pvalue > signif_level and factor != 'const':
                    all_pvals_under = False
                    temp_factor_df = temp_factor_df.drop(
                        columns=factor, axis=1)

            if results.rsquared_adj >= r2_threshold and all_pvals_under:
                if (portfolios.get(str(factor))) is None:
                    portfolios[str(factor)] = set([ticker])
                else:
                    portfolios[str(factor)].add(ticker)

                to_remove = [
                    col for col in factor_test_df.columns if col not in temp_factor_df.columns]
                factor_test_temp_df = factor_test_df.drop(to_remove, axis=1)
                prediction_df, mse = test_model(
                    results, factor_test_temp_df, stock_test_df)
                reg_prediction_df, reg_mse = test_regularized_model(
                    model, 0.01, stock_test_df, factor_test_temp_df)

                if outputToExcel:
                    add_to_output_files(ticker, prediction_df)
                    add_to_output_files(ticker, reg_prediction_df,
                                        regularization_check=True)

                print(f"Prediction Mean Squared Error: {mse}")
                print(f"Regularized Prediction Mean Squared Error: {reg_mse}")
                print(results.summary())

            if all_pvals_under:
                pvals_under_sig = True

    return portfolios


def debug_shape(dfs):
    for df in dfs:
        print(df.shape)


def add_factors_from_csv(directory) -> pd.DataFrame:
    """Takes a factor name and a CSV file, calculates the returns and returns them as a dataframe
    The first two elements should be a date column heading and a "Close" (case sensitive) column heading. 
    The data should be two columns corresponding to dates and closing prices. 
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
        combined_factors = combined_factors.join(
            df, on='Date', how='left', lsuffix='_left', rsuffix='_right')

    return combined_factors.apply(lambda factor: get_returns(factor))


def normalize_factor_dates(stock_factors):
    temp_stock = add_stock_from_tickers(['MSFT']) # Use any stock to normalize the rest
    return temp_stock.join(stock_factors, on='Date', how='left', lsuffix='_left', rsuffix='_right') \
        .drop('MSFT', axis=1)


# Retrieving a list of all of the stocks in the S&P 500 index and putting them in a list
def save_sp500_tickers():
    resp = requests.get(
        'http://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
    soup = bs.BeautifulSoup(resp.text, 'lxml')
    table = soup.find('table', {'class': 'wikitable sortable'})
    tickers = []
    for row in table.findAll('tr')[1:]:
        ticker = row.findAll('td')[0].text
        ticker = ticker.replace('\n', '')
        tickers.append(ticker)

    return tickers


def get_n_random_stocks(n: int):
    stock_list = save_sp500_tickers()
    random.shuffle(stock_list)
    return stock_list[:n]

def summarize(portfolios: dict):
    print('\nThe price of the following tickers is correlated with the value of an economic factor to a statistically significant degree:')
    for factor, correlations in portfolios.items():
        print(f'\t{correlations} {"are" if len(correlations) > 1 else "is"} correlated with the {factor} factor')


if __name__ == '__main__':
    stocks_to_analyze = get_n_random_stocks(10)

    stocks = add_stock_from_tickers(stocks_to_analyze)
    factors = add_factors_from_csv('../factorDirectory/')

    normalizedFactors = normalize_factor_dates(factors)

    for column in normalizedFactors.columns:
        if column == 'Close':
            normalizedFactors = normalizedFactors.drop(columns=column, axis=1)

    portfolios = regress_factors(stocks, normalizedFactors)
    summarize(portfolios)
