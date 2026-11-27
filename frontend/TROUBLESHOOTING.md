# Frontend Troubleshooting Guide

## Prerequisites
- Node.js and npm installed.
- Dependencies installed using npm.cmd install.

## Start the application
npm.cmd run dev

## Run unit tests
npm.cmd test -- --run

## Run end-to-end tests
npm.cmd run test:e2e

## Install Playwright browser
npx.cmd playwright install chromium

## Production build
npm.cmd run build

## Common issues
- If PowerShell blocks npm, use npm.cmd instead of npm.
- If Playwright cannot find Chromium, install it using the command above.
- If the backend is unavailable, check that the backend service is running.
- If tests fail, inspect the failing test and its error message.
- Demo mode uses simulated data and does not confirm live backend execution.

## Before release
Run unit tests, end-to-end tests, accessibility checks, and the production build.
