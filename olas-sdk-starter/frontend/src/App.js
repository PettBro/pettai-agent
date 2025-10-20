import React, { useState, useEffect, useMemo } from 'react';
import {
  BrowserRouter,
  Routes,
  Route,
  useNavigate,
  useLocation,
} from 'react-router-dom';
import { PrivyProvider } from '@privy-io/react-auth';
import { AuthProvider, useAuth } from './providers/AuthProvider';
import LoginPage from './pages/LoginPage';
import Dashboard from './pages/Dashboard';
import AllSet from './pages/AllSet';
import './assets/styles/core.scss';
import './assets/styles/toast.scss';
import './assets/styles/tutorial.scss';
import './assets/styles/modals.scss';
import './assets/styles/button.scss';
import './assets/fonts/retro-pixel.css';
import './assets/fonts/satoshi.css';
import './App.css';

// Router component with navigation logic
const RouterWithAuth = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { authenticated, ready, wsPet } = useAuth();

  // Navigate to All Set screen on successful authentication (only from login page)
  useEffect(() => {
    if (
      authenticated &&
      ready &&
      wsPet &&
      (location.pathname === '/login' || location.pathname === '/')
    ) {
      console.log('[App] Authentication successful, navigating to all-set');
      navigate('/all-set', { replace: true });
    }
  }, [authenticated, ready, wsPet, navigate, location.pathname]);

  // Redirect to login if authentication is lost
  useEffect(() => {
    if (
      ready &&
      !authenticated &&
      location.pathname !== '/login' &&
      location.pathname !== '/'
    ) {
      console.warn('[App] Authentication lost, redirecting to login');
      navigate('/login', { replace: true });
    }
  }, [ready, authenticated, navigate, location.pathname]);

  return (
    <Routes>
      <Route path="/" element={<LoginPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/all-set" element={<AllSet />} />
    </Routes>
  );
};

// Main app router with loading states
const AppRouter = () => {
  const routingComponent = useMemo(
    () => (
      <div className="App-content">
        <BrowserRouter>
          <RouterWithAuth />
        </BrowserRouter>
      </div>
    ),
    []
  );

  return routingComponent;
};

// Main App component
function App() {
  return (
    <div className="App">
      <PrivyProvider
        appId={
          process.env.REACT_APP_PRIVY_APP_ID || 'cm7gev5s600vbk2lsj6e1e9g7'
        }
        config={{
          loginMethods: ['telegram', 'email', 'wallet'],
          appearance: {
            theme: 'light',
            accentColor: '#4A90E2',
          },
        }}
      >
        <AuthProvider>
          <AppRouter />
        </AuthProvider>
      </PrivyProvider>
    </div>
  );
}

export default App;
