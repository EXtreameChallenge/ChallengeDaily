// 启动 Electron 开发模式，强制 ELECTRON_IS_DEV=1
// 用于解决 dist/index.html 存在时 isDev 误判为 false 的问题
const { spawn } = require('child_process')
const electron = require('electron')

const env = { ...process.env, ELECTRON_IS_DEV: '1' }
const child = spawn(electron, ['.'], {
  stdio: 'inherit',
  env,
  shell: true
})

child.on('close', (code) => process.exit(code))
