/**
 * AuthProvider - Fixed for Electron iframe popup issue
 */

import React, {
	createContext,
	useCallback,
	useContext,
	useEffect,
	useMemo,
	useState,
	useRef,
} from 'react';
import { usePrivy } from '@privy-io/react-auth';
import { useAuthMessageListener } from '../hooks/useAuthMessageListener';

const AuthContext = createContext(null);

const isElectron = () => {
	if (typeof window === 'undefined') return false;
	return !!(
		window.process?.versions?.electron ||
		window.navigator?.userAgent?.includes('Electron') ||
		window.electronAPI ||
		window.navigator?.userAgent?.toLowerCase().includes('electron')
	);
};

const isInIframe = () => {
	if (typeof window === 'undefined') return false;
	try {
		return window.self !== window.top;
	} catch (e) {
		return true;
	}
};

export const AuthProvider = ({ children }) => {
	const { ready, logout: privyLogout } = usePrivy();

	const [privyToken, setPrivyToken] = useState(null);
	const [wsPet, setWsPet] = useState(null);
	const [isLoggingIn, setIsLoggingIn] = useState(false);
	const [loginError, setLoginError] = useState(null);
	const [popupStatus, setPopupStatus] = useState(null);

	const popupRef = useRef(null);

	const authenticated = !!privyToken && !!wsPet;

	// Detect if we're in an Electron iframe
	const inElectronIframe = useMemo(() => isInIframe() && isElectron(), []);

	const authenticateWithBackend = useCallback(async (token) => {
		if (!token) return;

		try {
			const response = await fetch('/api/login', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ privy_token: token }),
			});
			const data = await response.json();

			const petConnected = data?.pet_connected === true || data?.pet?.connected === true;
			const petName = data?.pet_name || data?.pet?.name;

			if (!response.ok || data?.success !== true) {
				console.error('[AuthProvider] Backend login failed:', data);

				if (petConnected && petName) {
					setWsPet(petName);
					setPrivyToken(token);
					setLoginError(null);
					setIsLoggingIn(false);
					setPopupStatus({ status: 'completed', message: 'Connected.', timestamp: Date.now() });
					try { popupRef.current?.close(); } catch (e) { }
					popupRef.current = null;
					return;
				}

				setWsPet(null);
				setLoginError(data?.message || 'Backend login failed.');
				setIsLoggingIn(false);
				setPopupStatus({ status: 'error', message: data?.message || 'Login failed.', timestamp: Date.now() });
				return;
			}

			console.log('[AuthProvider] Backend login successful');
			setWsPet(data.name || 'Connected');
			setPrivyToken(token);
			setLoginError(null);
			setIsLoggingIn(false);
			setPopupStatus({ status: 'completed', message: 'Authenticated.', timestamp: Date.now() });
			try { popupRef.current?.close(); } catch (e) { }
			popupRef.current = null;
		} catch (error) {
			console.error('[AuthProvider] Error:', error);
			setWsPet(null);
			setLoginError(error?.message || 'Authentication failed.');
			setIsLoggingIn(false);
		}
	}, []);

	useAuthMessageListener({
		onToken: (token) => {
			console.log('[AuthProvider] Token received');
			authenticateWithBackend(token);
		},
		onError: (error) => {
			setLoginError(error?.message || 'Login failed.');
			setIsLoggingIn(false);
		},
		onPopupClosed: () => {
			setIsLoggingIn(false);
			popupRef.current = null;
		},
		onStatusChange: (status, message) => {
			setPopupStatus({ status, message: message || '', timestamp: Date.now() });
		},
	});

	useEffect(() => {
		let isMounted = true;
		const restoreSession = async () => {
			try {
				const response = await fetch('/api/health');
				if (!response.ok) return;
				const data = await response.json();
				const isAuth = Boolean(data?.websocket?.authenticated) || Boolean(data?.pet?.connected);
				if (isAuth && isMounted) {
					setWsPet(data?.pet?.name || 'Connected');
				}
			} catch (e) { }
		};
		if (ready) restoreSession();
		return () => { isMounted = false; };
	}, [ready]);

	const cleanupPopup = useCallback(() => {
		if (popupRef.current) {
			try { if (!popupRef.current.closed) popupRef.current.close(); } catch (e) { }
			popupRef.current = null;
		}
		setIsLoggingIn(false);
	}, []);

	const openLoginPopup = useCallback(() => {
		cleanupPopup();

		const popupUrl = new URL('/privy-login', window.location.origin);
		const windowName = `privy-login-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
		const POPUP_FEATURES = 'width=420,height=720,resizable=yes,scrollbars=yes,menubar=no,toolbar=no,location=no,status=no';

		setIsLoggingIn(true);
		setLoginError(null);

		console.log('[AuthProvider] Opening popup', { inElectronIframe });

		const popup = window.open(popupUrl.toString(), windowName, POPUP_FEATURES);

		if (popup) {
			popupRef.current = popup;
			setPopupStatus({ status: 'opening', message: 'Opening login…', timestamp: Date.now() });
			popup.focus();

			const checkClosed = setInterval(() => {
				try {
					if (!popupRef.current || popupRef.current.closed) {
						clearInterval(checkClosed);
						setIsLoggingIn(false);
						popupRef.current = null;
					}
				} catch (e) { }
			}, 500);
		} else {
			setPopupStatus({ status: 'error', message: 'Popup blocked.', timestamp: Date.now() });
			setLoginError('Unable to open login window. Please allow popups.');
			setIsLoggingIn(false);
		}
	}, [cleanupPopup, inElectronIframe]);

	const login = useCallback(() => {
		openLoginPopup();
	}, [openLoginPopup]);

	/**
	 * SOFT LOGOUT - The key fix!
	 * 
	 * In Electron iframe context, we DON'T call Privy's logout() because it
	 * clears state that Electron needs to intercept popups.
	 * 
	 * Instead, we just:
	 * 1. Clear our app state
	 * 2. Call backend logout
	 * 
	 * The PrivyLoginPopup already calls logout() on mount, so Privy will
	 * get a clean state when the user opens the login popup again.
	 */
	const logout = useCallback(async () => {
		console.log('[AuthProvider] Logging out (soft logout for Electron)');

		// Call backend logout
		try {
			await fetch('/api/logout', { method: 'POST' });
		} catch (e) {
			console.warn('[AuthProvider] Backend logout failed:', e);
		}

		// Clear our app state
		setPrivyToken(null);
		setWsPet(null);
		setPopupStatus(null);
		setLoginError(null);
		cleanupPopup();

		// CRITICAL: In Electron iframe, DON'T call Privy logout
		// This preserves whatever state Electron uses to intercept popups
		if (!inElectronIframe) {
			try {
				await privyLogout();
			} catch (error) {
				console.warn('[AuthProvider] Privy logout error:', error);
			}
		} else {
			console.log('[AuthProvider] Skipping Privy logout to preserve Electron popup context');
		}

		console.log('[AuthProvider] Logout complete');
	}, [privyLogout, cleanupPopup, inElectronIframe]);

	const loginAfterLogout = useCallback(async () => {
		console.log('[AuthProvider] Login after logout');
		await logout();
		setTimeout(() => openLoginPopup(), 100);
	}, [logout, openLoginPopup]);

	const value = useMemo(() => ({
		ready,
		authenticated,
		user: null,
		wsPet,
		isModalOpen: isLoggingIn,
		authError: loginError,
		authFailed: !!loginError,
		popupStatus,
		isElectron: isElectron(),
		isIframe: isInIframe(),
		login,
		logout,
		loginAfterLogout,
	}), [
		ready, authenticated, wsPet, isLoggingIn, loginError, popupStatus,
		login, logout, loginAfterLogout,
	]);

	return (
		<AuthContext.Provider value={value}>
			{children}
		</AuthContext.Provider>
	);
};

export const useAuth = () => {
	const context = useContext(AuthContext);
	if (!context) {
		throw new Error('useAuth must be used within an AuthProvider');
	}
	return context;
};

export default AuthProvider;