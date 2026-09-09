import asyncio
import time
from .config import public_config
from .connectors import platform_tools
from .runtime import create_run
from .tools import ToolContext


async def check_platforms():
    async def check(source):
        if not public_config()['connectors'][source]:
            return {'platform': source, 'status': 'not_configured', 'message': '尚未配置实例地址与 API 凭据'}
        started = time.monotonic()
        try:
            tools = {t.name: t for t in platform_tools(source)}
            context = ToolContext(create_run({'scenario': 'finance' if source == 'erpnext' else 'support', 'mode': 'live', 'source': source, 'task': 'Connection check'}))
            probes = [('erpnext_list_invoices', {'status': 'all', 'page': 1, 'pageSize': 1}), ('erpnext_list_payments', {'page': 1, 'pageSize': 1})] if source == 'erpnext' else [('zammad_list_tickets', {'page': 1, 'pageSize': 1}), ('zammad_list_states', {})]
            for name, args in probes:
                await tools[name].execute(args, context)
            return {'platform': source, 'status': 'reachable', 'latencyMs': round((time.monotonic() - started) * 1000), 'message': 'Python 连接器已验证两个只读端点'}
        except Exception as error:
            return {'platform': source, 'status': 'failed', 'message': str(error)[:500]}
    return await asyncio.gather(check('erpnext'), check('zammad'))


if __name__ == '__main__':
    import json
    print(json.dumps(asyncio.run(check_platforms()), ensure_ascii=False, indent=2))
