"""OpenAPI tool acquisition and intent retrieval over short tool descriptions."""
from copy import deepcopy
import hashlib
import json
import re
import math
from collections import Counter
from urllib.parse import quote
from .tools import Tool, object_schema

UNSAFE = {'__proto__', 'constructor', 'prototype'}


def intent_tokens(text):
    words = re.findall(r'[a-z0-9]+', text.lower())
    for phrase in re.findall(r'[\u4e00-\u9fff]+', text):
        words.extend(phrase[i:i+2] for i in range(max(0, len(phrase)-1)))
    return words


def retrieve_tools(intent, tools, k=4):
    """Local BM25 over concise tool descriptions, not a semantic embedding model."""
    docs = [Counter(intent_tokens(t.name.replace('_', ' ') + ' ' + t.description)) for t in tools]
    query = set(intent_tokens(intent))
    mean = sum(sum(d.values()) for d in docs) / max(1, len(docs))
    df = Counter(word for doc in docs for word in doc)
    ranked = []
    for tool, doc in zip(tools, docs):
        score = 0.0
        for term in query:
            freq = doc[term]
            if freq:
                idf = math.log(1 + (len(docs) - df[term] + .5) / (df[term] + .5))
                score += idf * freq * 2.2 / (freq + 1.2 * (.25 + .75 * sum(doc.values()) / max(mean, 1)))
        ranked.append(dict(name=tool.name, score=round(score, 5)))
    return sorted(ranked, key=lambda r: (-r['score'], r['name']))[:k]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def path_value(value, path):
    for part in path:
        if part in UNSAFE:
            raise ValueError('Unsafe graph path')
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and str(part).isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            raise ValueError('图参数路径不存在：' + '.'.join(path))
    return value


def acquire_tools(spec, transport, observe):
    if spec.get('openapi') != '3.0.3' or not spec.get('info', {}).get('title'):
        raise ValueError('Unsupported OpenAPI specification')
    result, names = [], set()
    for path, methods in spec['paths'].items():
        if not path.startswith('/api/') or '..' in path or '?' in path or set(methods) != {'get'}:
            raise ValueError('AutoTool only permits configured GET API paths')
        op = methods['get']
        name = op['operationId']
        if not re.fullmatch('[a-z][a-z0-9_]{0,63}', name) or name in names:
            raise ValueError('Duplicate or invalid operation ID')
        names.add(name)
        properties, required = {}, []
        for parameter in op['parameters']:
            key, schema = parameter['name'], deepcopy(parameter['schema'])
            if key in UNSAFE or key in properties or not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,63}', key) or parameter['in'] not in ['path', 'query'] or parameter['required'] is not True:
                raise ValueError('Unsupported or unsafe OpenAPI parameter')
            if schema['type'] not in ['string', 'integer', 'number', 'boolean']:
                raise ValueError('Unsupported OpenAPI parameter type')
            if schema['type'] == 'string':
                schema.setdefault('minLength', 1)
                schema.setdefault('maxLength', 500)
            properties[key] = schema
            required.append(key)
        placeholders = set(re.findall(r'\{([^}]+)\}', path))
        if placeholders != {p['name'] for p in op['parameters'] if p['in'] == 'path'}:
            raise ValueError('OpenAPI path parameters do not match placeholders')

        async def handler(args, context, path=path, op=op):
            query = {}
            for parameter in op['parameters']:
                value = args[parameter['name']]
                value = str(value).lower() if isinstance(value, bool) else str(value)
                if parameter['in'] == 'path':
                    if value in ['.', '..']:
                        raise ValueError('Dot segments are not valid record identifiers')
                    path = path.replace('{' + parameter['name'] + '}', quote(value, safe=''))
                else:
                    query[parameter['name']] = value
            response = await transport(path, query)
            data = path_value(response, op.get('x-data-path', []))
            return observe(data, op['x-resource'], context)

        result.append(Tool(name, op['summary'], 'read', object_schema(properties, required), handler,
                           {'kind': 'autotool', 'spec': spec['info']['title'], 'operationId': name, 'digest': digest(spec)}))
    return result
