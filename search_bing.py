import requests
from flask import Flask
from flask import request

from utils import Baidu_translate
import random
import time

import myConfig
app = Flask(__name__)

@app.route("/bing_search", methods=['GET', 'POST'])
def search_bing():
    started = time.time()
    search_url = 'https://api.bing.microsoft.com/v7.0/search'

    data = request.form
    print(data)
    q = data['q']
    n = data['n']

    h = {'Ocp-Apim-Subscription-Key':  myConfig.auth_key, 'Accept-Language': 'English'}
    params = {'q': q, 'count': n, 'cc': 'US', 'ensearch': '1', 'responseFilter': 'Webpages',
              "textDecorations": True, "textFormat": "HTML"}
    # print(f"searching {q} for {n} results")
    response = requests.get(search_url, headers=h, params=params)
    if response.status_code == 200:
        response = response.json()
        value = response.get('webPages', None)
        if value:
            value = value.get('value', None)
        else:
            return None
        mid_list = []
        for item in value:
            mid_list.append(
                {
                    'url': item['url'],
                    'title': item['name'],
                    'content': item['snippet'],
                }
            )
        # todo 通过字符串replace的方式替换key值
        response_reply = {
            'status_code': 200,
            'response': mid_list
        }
        cost = time.time() - started
        print(f"search cost {cost:.4f}s")
        return response_reply
    return None

# 修改为deepl的翻译 20220428
@app.route("/baidu_translate", methods=("GET", "POST"))
def _translate():
    started = time.time()
    url = 'https://api-free.deepl.com/v2/translate'
    data = request.args.to_dict()
    content = data['content']
    target_lang = data['toLang']
    req_url = url + '?auth_key=640de6ab-efc2-90c5-7306-cabea0e2e15a:fx&text=' + content + '&target_lang='+ target_lang
    output = requests.get(req_url).json()
    print(output)
    cost = time.time() - started
    print(f"translate cost {cost:.4f}s")
    return output['translations'][0]['text']

# def _translate():
#     started = time.time()
#     url = 'https://api.fanyi.baidu.com/api/trans/vip/translate'
#     data = request.args.to_dict()
#     ori_input = {'salt': random.randint(1, 2022),
#                  'appid': '20220211001079919',
#                  'secret_key': 'dTWhdYJ0lxsZAGlVDH8D',
#                  'content': data['content'],
#                  'from': data['fromLang'],
#                  'to': data['toLang']}
#
#     output = Baidu_translate.trans(url, ori_input)
#     print(output)
#     cost = time.time() - started
#     print(f"translate cost {cost:.4f}s")
#     return output['dst']


# @app.route("/test", methods=['GET', 'POST'])
# def test():
#     print(request.args)
#     return "test successfully"


if __name__ == "__main__":
    app.run(debug=True, port=myConfig.port, host=myConfig.host)

