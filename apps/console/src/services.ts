// Service names for the visit form, bundled from the read-only data/services.json at build time.
// The active catalog lives in D1; if it changes, rebuild the console or type the service id by hand.
import data from '../../../data/services.json';

export interface ServiceOption {
  id: string;
  name: string;
}

interface RawService {
  id: string;
  name_vi?: string;
}

export const SERVICES: ServiceOption[] = ((data as { services: RawService[] }).services ?? []).map((s) => ({
  id: s.id,
  name: s.name_vi ?? s.id,
}));
