#!/usr/bin/env node
'use strict';
// Keep the npm entry point; the shared page writer owns the conversion policy.
const {spawnSync} = require('node:child_process');
const path = require('node:path');
const result = spawnSync('python3', ['scripts/install_clarity.py'], {cwd: path.resolve(__dirname, '..'), stdio: 'inherit'});
if (result.error) console.error(result.error.message);
process.exit(result.status ?? 1);
