import React, { useEffect, useRef, useState } from 'react';
import Button from '../components/ui/Button';
import { usePrivyModalHeight } from '../hooks/usePrivyModalHeight';
import { useAuth } from '../providers/AuthProvider';
import './LoginPage.scss';
import background1 from '../assets/images/background-1.jpg';
import floating1 from '../assets/images/floating-1.png';
import floating2 from '../assets/images/floating-2.png';
import { useNavigate } from 'react-router-dom';

const LoginPage = () => {
	const { login, isModalOpen, wsPet, authFailed } = useAuth();
	const hasCalledLogin = useRef(false);
	const privyModalHeight = usePrivyModalHeight();
	const navigate = useNavigate();
	const [debugInfo, setDebugInfo] = useState('Mounted');

	// DEBUG: Log state changes
	useEffect(() => {
		console.log('[LoginPage DEBUG]', {
			isModalOpen,
			wsPet,
			authFailed,
			hasCalledLogin: hasCalledLogin.current
		});
		setDebugInfo(`Modal: ${isModalOpen}, Pet: ${wsPet}, Failed: ${authFailed}`);
	}, [isModalOpen, wsPet, authFailed]);

	// DISABLED AUTO-LOGIN FOR DEBUGGING
	// Only trigger login on button click
	const handleLogin = () => {
		console.log('[LoginPage] Manual login triggered');
		login();
	};

	// Redirect to All Set if already logged in (token established)
	useEffect(() => {
		if (wsPet !== null) {
			console.log('[LoginPage] Navigating to all-set, wsPet:', wsPet);
			navigate('/all-set', { replace: true });
		}
	}, [wsPet, navigate]);

	return (
		<div
			className="login-screen relative top-0 left-0 h-dvh px-6 pb-6 w-full  overflow-hidden"
			style={{
				'--privy-modal-height': privyModalHeight > 0 ? `${privyModalHeight}px` : '0',
				paddingTop: 'calc(var(--safe-area-inset-top) + 4rem)',
				paddingBottom: 'calc(var(--safe-area-inset-bottom) + 1.5rem)',
			}}
		>
			<div className="absolute z-[4] text-white text-sm leading-relaxed login-screen__intro left-6 right-6">
				<p className="bg-black bg-opacity-30 px-4 py-3 rounded-lg backdrop-blur-sm">
					<strong>DEBUG MODE:</strong> Auto-login disabled. Click the button below to login manually.
					<br />
					<small>{debugInfo}</small>
				</p>
			</div>
			<h1 className="absolute login-screen__title z-[3] text-white text-4xl text-center left-6 right-6">
				Let's Get <br />
				Started
			</h1>
			<img
				className="absolute top-0 left-0 w-full h-full z-0 object-cover object-top"
				src={background1}
				alt="Login Screen"
			/>
			<img
				className="login-screen__floating--top w-[197px] absolute z-[1] top-[6%] right-0"
				src={floating2}
				alt="magical floating stars"
			/>
			<img
				className="login-screen__floating--bottom w-[166px] absolute z-[2] left-0"
				src={floating1}
				alt="rocket"
			/>

			<div
				className="absolute bottom-6 left-6 right-6 z-[4]"
				style={{ paddingBottom: 'calc(var(--safe-area-inset-bottom) + 1.5rem)' }}
			>
				<Button onClick={handleLogin} disabled={wsPet !== null} className="w-full">
					{authFailed ? 'Retry Login' : 'Login (Debug Mode)'}
				</Button>
				<p className="text-white text-center mt-2 text-xs">
					Check browser console for debug info
				</p>
			</div>
		</div>
	);
};

export default LoginPage;

