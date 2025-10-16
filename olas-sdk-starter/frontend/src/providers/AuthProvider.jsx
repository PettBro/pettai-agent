import React, { createContext, useContext, useState, useEffect } from 'react';
import { usePrivy } from '@privy-io/react-auth';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
	const {
		ready,
		login,
		isModalOpen,
		user: privyUser,
		logout: privyLogout,
		authenticated: privyAuthenticated,
		getAccessToken: privyGetAccessToken,
	} = usePrivy();


	const [wsPet, setWsPet] = useState(null);
	const [authFailed, setAuthFailed] = useState(false);

	// Get and log Privy token when authenticated
	useEffect(() => {
		const getToken = async () => {
			if (privyAuthenticated && privyUser) {
				try {
					console.log('[Auth] Getting Privy access token');
					// Get the Privy access token
					const token = await privyGetAccessToken();
					console.log('[Auth] Privy access token:', token);

					// Send token to Python backend to authenticate WebSocket
					const response = await fetch('/api/login', {
						method: 'POST',
						headers: { 'Content-Type': 'application/json' },
						body: JSON.stringify({ privy_token: token }),
					});
					const data = await response.json();

					if (!response.ok || data?.success !== true) {
						console.error('[Auth] Backend login failed:', data);
						setAuthFailed(true);
						return;
					}

					console.log('[Auth] Backend login successful:', data);

					// Mark pet connection as established (string used by router logic)
					setWsPet(data.name || 'Connected');
					setAuthFailed(false);
				} catch (error) {
					console.error('[Auth] Error getting Privy token:', error);
					setAuthFailed(true);
				}
			}
		};

		if (privyAuthenticated && ready) {
			getToken();
		}
	}, [privyAuthenticated, ready, privyUser, privyGetAccessToken]);


	// Combined logout: clear backend token, then Privy
	const logout = async () => {
		try {
			await fetch('/api/logout', { method: 'POST' });
		} catch (e) {
			console.warn('[Auth] Backend logout failed (continuing):', e);
		}
		try {
			await privyLogout();
		} finally {
			setWsPet(null);
			setAuthFailed(false);
		}
	};

	const value = {
		login,
		logout,
		authenticated: privyAuthenticated,
		ready,
		user: privyUser,
		wsPet,
		authFailed,
		isModalOpen,
	};

	return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
	const context = useContext(AuthContext);
	if (!context) {
		throw new Error('useAuth must be used within AuthProvider');
	}
	return context;
};

