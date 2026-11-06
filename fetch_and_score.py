import json, csv, os, re, time, math, datetime as dt, html
from html.parser import HTMLParser
from urllib.parse import quote_plus
from component_scoring import (
    DEFAULT_COMPONENT_WEIGHTS, build_component, combine_components,
    search_component_from_snapshot, client_oi_context, is_fresh_timestamp,
    compare_mcx_bhavcopy_contract_oi,
)
import feedparser, yfinance as yf
import requests
from curl_cffi import requests as curl_requests

# ---- इंडेक्स और कमोडिटी ----