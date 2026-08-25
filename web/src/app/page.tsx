import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Study } from '@/components/Study';
import type { Cube, Strip } from '@/lib/types';
import stripJson from '@/data/v6_strip.json';

/**
 * Server component. The cube is read from public/ at build time rather than
 * imported, so a rebuilt cube does not need a code change — and it stays a
 * single file the browser could also fetch if the page ever needs to lazy-load
 * a variant.
 */
function readCube(): Cube {
  return JSON.parse(
    readFileSync(join(process.cwd(), 'public', 'cube.json'), 'utf8'),
  ) as Cube;
}

export default function Page() {
  return <Study cube={readCube()} strip={stripJson as unknown as Strip} />;
}
