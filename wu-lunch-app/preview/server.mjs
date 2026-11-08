import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve, extname, sep} from 'node:path';

const root = resolve(import.meta.dirname);
const port = Number(process.env.PORT || 4173);
const contentTypes = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8'};

createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
    const path = pathname === '/restaurant-contact.json'
      ? resolve(root, '../../wu-lunch/data/restaurant-contact.json')
      : resolve(root, '.' + (pathname === '/' ? '/index.html' : pathname));
    if (pathname !== '/restaurant-contact.json' && path !== root && !path.startsWith(root + sep)) throw new Error('Invalid path');
    const content = await readFile(path);
    response.writeHead(200, {'Content-Type': contentTypes[extname(path)] || 'application/octet-stream'});
    response.end(content);
  } catch {
    response.writeHead(404);
    response.end('Not found');
  }
}).listen(port, '127.0.0.1', () => console.log(`WU Food preview: http://localhost:${port}`));
