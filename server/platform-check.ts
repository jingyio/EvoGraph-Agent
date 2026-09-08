import './config.js';
import { pathToFileURL } from 'node:url';
import { publicConfig } from './config.js';
import { platformTools } from './connectors.js';
import { createRun, errorMessage } from './runtime.js';

export async function checkPlatforms() {
  return Promise.all((['erpnext', 'zammad'] as const).map(async source => {
    if (!publicConfig().connectors[source]) return { platform: source, status: 'not_configured', message: '尚未配置实例地址与 API 凭据' };
    const start = Date.now();
    try {
      const tools = platformTools(source);
      const run = createRun({ scenario: source === 'erpnext' ? 'finance' : 'support', source, mode: 'live', task: 'Read-only connectivity check' }, null);
      const context = { run, signal: AbortSignal.timeout(20000), evidence: new Set<string>() };
      const probes = source === 'erpnext' ? [{ name: 'erpnext_list_invoices', args: { status: 'all', page: 1, pageSize: 1 } }, { name: 'erpnext_list_payments', args: { page: 1, pageSize: 1 } }] : [{ name: 'zammad_list_tickets', args: { page: 1, pageSize: 1 } }, { name: 'zammad_list_states', args: {} }];
      for (const probe of probes) await tools.find(tool => tool.name === probe.name)!.execute(probe.args, context);
      return { platform: source, status: 'reachable', latencyMs: Date.now() - start, message: `已验证 ${probes.length} 个只读端点；数据初始化和完整权限仍需单独核查` };
    } catch (error) { return { platform: source, status: 'failed', latencyMs: Date.now() - start, message: errorMessage(error) }; }
  }));
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) console.log(JSON.stringify(await checkPlatforms(), null, 2));
