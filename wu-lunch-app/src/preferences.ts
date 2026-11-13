export type AppLanguage = 'de' | 'en';
type Storage = {getItem(key: string): Promise<string | null>; setItem(key: string, value: string): Promise<unknown>};
const key = 'wu-lunch-language';
export function languagePreferences(storage: Storage) {
  let pending = Promise.resolve<unknown>(undefined);
  return {
    async load(): Promise<AppLanguage | null> {try {const value = await storage.getItem(key); return value === 'de' || value === 'en' ? value : null;} catch {return null;}},
    save(value: AppLanguage) {pending = pending.catch(() => {}).then(() => storage.setItem(key, value)); return pending;},
  };
}
