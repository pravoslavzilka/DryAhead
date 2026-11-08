import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { LangContext } from '../blue/ui'
import '../blue/blue.css'
import './about.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <LangContext.Provider value="en">
      <App />
    </LangContext.Provider>
  </React.StrictMode>,
)
