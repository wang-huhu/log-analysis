import json

import requests

from models import AppConfig


_DEFAULT_HEADERS = {
    "cache-control": "no-cache",
    "connection": "keep-alive",
    "kbn-version": "7.7.0",
    "referer": "https://k8s-elk.memeyule.com/app/kibana",
    "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "content-type": "application/json",
    "accept": "*/*",
    "host": "k8s-elk.memeyule.com",
}


def _build_payload(start_time: str, end_time: str) -> dict:
    return {
        "params": {
            "ignoreThrottled": True,
            "preference": 1776759662080,
            "index": "k8s-nnsg-test-meme-back-lumo-api-*",
            "body": {
                "version": True,
                "size": 500,
                "sort": [{"@timestamp": {"order": "desc", "unmapped_type": "boolean"}}],
                "aggs": {
                    "2": {
                        "date_histogram": {
                            "field": "@timestamp",
                            "fixed_interval": "1s",
                            "time_zone": "Asia/Shanghai",
                            "min_doc_count": 1,
                        }
                    }
                },
                "stored_fields": ["*"],
                "script_fields": {},
                "docvalue_fields": [
                    {"field": "@timestamp", "format": "date_time"},
                    {"field": "logdatetime", "format": "date_time"},
                ],
                "_source": {"excludes": []},
                "query": {
                    "bool": {
                        "must": [],
                        "filter": [
                            {"multi_match": {"type": "best_fields", "query": "error", "lenient": True}},
                            {
                                "range": {
                                    "@timestamp": {
                                        "gte": start_time,
                                        "lte": end_time,
                                        "format": "strict_date_optional_time",
                                    }
                                }
                            },
                        ],
                        "should": [],
                        "must_not": [],
                    }
                },
                "highlight": {
                    "pre_tags": ["@kibana-highlighted-field@"],
                    "post_tags": ["@/kibana-highlighted-field@"],
                    "fields": {"*": {}},
                    "fragment_size": 2147483647,
                },
            },
        },
        "rest_total_hits_as_int": True,
        "ignore_unavailable": True,
        "ignore_throttled": True,
        "timeout": "30000ms",
    }


def fetch_logs(config: AppConfig, start_time: str, end_time: str) -> dict:
    try:
        response = requests.post(
            config.log_api_url,
            headers=_DEFAULT_HEADERS,
            data=json.dumps(_build_payload(start_time, end_time)),
            timeout=30,
        )
    except requests.Timeout as exc:
        raise RuntimeError("日志接口请求超时") from exc
    except requests.RequestException as exc:
        raise RuntimeError("日志接口请求失败") from exc

    if response.status_code != 200:
        raise RuntimeError(f"日志接口返回异常状态码: {response.status_code}")

    return response.json()
