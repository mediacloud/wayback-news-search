import datetime as dt
from typing import List, Dict
import requests
import logging
import ciso8601
import waybacknews.util as util

VERSION = "v1"  # the API access URL is versioned for future compatability and maintenance


class SearchApiClient:

    API_BASE_URL = "https://wayback-api.archive.org/colsearch/{}/".format(VERSION)

    # constants used when requesting top terms
    TERM_FIELD_TITLE = "title"
    TERM_FIELD_SNIPPET = "snippet"
    TERM_AGGREGATION_TOP = "top"
    TERM_AGGREGATION_SIGNIFICANT = "significant"
    TERM_AGGREGATION_RARE = "rare"

    def __init__(self, collection: str, api_base_url: str = None):
        """
        :param collection: the archive support multiple collections of stories so you have to pass in the
                           name of the collection you want to search against
        :param api_base_url: advanced optional arg: let you override the hard-coded base URL
        """
        self._collection = collection
        if api_base_url:
            self.API_BASE_URL = api_base_url
        self._session = requests.Session()  # better performance to put all HTTP through this one object
        self._logger = logging.getLogger(__name__)

    def sample(self, query: str, start_date: dt.datetime, end_date: dt.datetime, **kwargs) -> List[Dict]:
        results = self._overview_query(query, start_date, end_date, **kwargs)
        if self._is_no_results(results):
            return []
        return results['matches']

    def top_sources(self, query: str, start_date: dt.datetime, end_date: dt.datetime, **kwargs) -> List[Dict]:
        results = self._overview_query(query, start_date, end_date, **kwargs)
        if self._is_no_results(results):
            return []
        return util.dict_to_list(results['topdomains'])

    def top_tlds(self, query: str, start_date: dt.datetime, end_date: dt.datetime, **kwargs) -> List[Dict]:
        results = self._overview_query(query, start_date, end_date, **kwargs)
        if self._is_no_results(results):
            return []
        return util.dict_to_list(results['toptlds'])

    def top_languages(self, query: str, start_date: dt.datetime, end_date: dt.datetime, **kwargs) -> List[Dict]:
        results = self._overview_query(query, start_date, end_date, **kwargs)
        if self._is_no_results(results):
            return []
        return util.dict_to_list(results['toplangs'])

    @staticmethod
    def _is_no_results(results: Dict) -> bool:
        return ('matches' not in results) and ('detail' in results) and (results['detail'] == 'No results found!')

    def count(self, query: str, start_date: dt.datetime, end_date: dt.datetime, **kwargs) -> int:
        results = self._overview_query(query, start_date, end_date, **kwargs)
        if self._is_no_results(results):
            return 0
        return results['total']

    def count_over_time(self, query: str, start_date: dt.datetime, end_date: dt.datetime, **kwargs) -> List:
        results = self._overview_query(query, start_date, end_date, **kwargs)
        if self._is_no_results(results):
            return []
        data = results['dailycounts']
        to_return = []
        # transform to list of dicts for easier use
        for day_date, day_value in data.items():  # date is in 'YYYY-MM-DD' format
            day = ciso8601.parse_datetime(day_date)
            to_return.append({
                'date': day,
                'timestamp': day.timestamp(),
                'count': day_value,
            })
        return to_return

    @staticmethod
    def _date_query_clause(start_date: dt.datetime, end_date: dt.datetime) -> str:
        return "publication_date:[{} TO {}]".format(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))

    def _overview_query(self, query: str, start_date: dt.datetime, end_date: dt.datetime, **kwargs) -> Dict:
        params = {"q": "{} AND {}".format(query, self._date_query_clause(start_date, end_date))}
        params.update(kwargs)
        results, response = self._query("{}/search/overview".format(self._collection), params, method='POST')
        return results

    def article(self, article_id: str) -> Dict:
        # you can extract article_ids from the `article_url` property
        results, _ = self._query("{}/article/{}".format(self._collection, article_id), method='GET')
        return results

    def all_articles(self, query: str, start_date: dt.datetime, end_date: dt.datetime, page_size: int = 1000, **kwargs):
        """
        @return: a generator that yeilds lists of articles, grouped by page.
        @Question: Should it return articles one by one, not by page? 
        """
        params = {"q": "{} AND {}".format(query, self._date_query_clause(start_date, end_date))}
        params.update(kwargs)
        more_pages = True
        while more_pages:
            page, response = self._query("{}/search/result".format(self._collection), params, method='POST')
            if self._is_no_results(page):
                yield []
            else:
                yield page
            # check if there is a link to the next page
            more_pages = False
            next_link_token = response.headers.get('x-resume-token')
            if next_link_token:
                params['resume'] = next_link_token
                more_pages = True

    def terms(self, query: str, start_date: dt.datetime, end_date: dt.datetime, field: str, aggregation: str, **kwargs) -> Dict:
        params = {"q": "{} AND {}".format(query, self._date_query_clause(start_date, end_date))}
        params.update(kwargs)
        results, response = self._query("{}/terms/{}/{}".format(self._collection, field, aggregation), params,
                                        method='GET')
        return results

    def _query(self, endpoint: str, params: Dict = None, method: str = 'GET'):
        """
        Centralize making the actual queries here for easy maintenance and testing of HTTP comms
        """
        if params and ('q' in params):
            params['q'] = util.sanitize_query(params['q'])
        endpoint_url = self.API_BASE_URL+endpoint
        if method == 'GET':
            r = self._session.get(endpoint_url, params=params)
        elif method == 'POST':
            r = self._session.post(endpoint_url, json=params)
        else:
            raise RuntimeError("Unsupported method of '{}'".format(method))
        
        if r.status_code >= 500:
            raise RuntimeError("API Server Error {}: a bad query string could have triggered this. Endpoint: {}, Params: {}".
                               format(r.status_code, endpoint_url, params))
                               
        return r.json(), r
