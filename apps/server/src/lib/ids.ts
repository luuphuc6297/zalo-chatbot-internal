// Owner: server-core. Prefixed, time-sortable ids: <prefix>_<12 hex ms><16 hex random>.
export type IdPrefix =
  | 'cus' | 'cns' | 'cpf' | 'cnv' | 'msg' | 'job' | 'drf' | 'tcl'
  | 'hof' | 'brq' | 'vis' | 'prm' | 'obx' | 'req' | 'ben' | 'chv' | 'chb';

export function newId(prefix: IdPrefix, now: number = Date.now()): string {
  const ts = now.toString(16).padStart(12, '0');
  const rnd = new Uint8Array(8);
  crypto.getRandomValues(rnd);
  return `${prefix}_${ts}${Array.from(rnd, (b) => b.toString(16).padStart(2, '0')).join('')}`;
}
