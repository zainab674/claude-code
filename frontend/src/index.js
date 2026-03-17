import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { ToastProvider } from './hooks/useToast';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<React.StrictMode><ToastProvider><App /></ToastProvider></React.StrictMode>);
