import React, { useEffect, useRef } from 'react';
import Button from '../components/ui/Button';
import { usePrivyModalHeight } from '../hooks/usePrivyModalHeight';
import { useAuth } from '../providers/AuthProvider';
import './LoginPage.scss';
import background1 from '../assets/images/background-1.jpg';
import floating1 from '../assets/images/floating-1.png';
import floating2 from '../assets/images/floating-2.png';
import { useNavigate } from 'react-router-dom';

const LoginPage = () => {
	const { login, isModalOpen, wsPet, authFailed, authenticated } = useAuth();
	const hasCalledLogin = useRef(false);
	const privyModalHeight = usePrivyModalHeight();
	const navigate = useNavigate();

	// Automatically show login modal on mount
	useEffect(() => {
		if (!hasCalledLogin.current) {
			hasCalledLogin.current = true;
			login();
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, []); // Remove login from dependencies

	// Redirect to All Set if already logged in (token established)
	useEffect(() => {
		if (wsPet !== null) {
			navigate('/all-set', { replace: true });
		}
	}, [wsPet, navigate]);

	useEffect(() => {
		if (!isModalOpen && hasCalledLogin.current) {
			login();
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [isModalOpen]);

	// Show loader while authenticating/connecting
	if (authenticated && wsPet === null) {
		return (
			<div className="h-dvh w-full flex flex-col items-center justify-center bg-global-grey-10">
				<div className="inline-block animate-spin rounded-full h-16 w-16 border-4 border-global-brand-60 border-t-transparent mb-4"></div>
				<p className="text-semantic-fg-base text-lg font-semibold">Connecting to your pet...</p>
				<p className="text-semantic-fg-muted text-sm mt-2">Please wait while we establish connection</p>
			</div>
		);
	}

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
					You can log in at <span className="font-semibold">app.pett.ai</span> even if you
					created your agent with Pearl. After logging in, well show a quick
					confirmation.
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
				<Button onClick={login} disabled={wsPet !== null} className="w-full">
					{authFailed ? 'Mint' : 'Login'}
				</Button>
			</div>
		</div>
	);
};

export default LoginPage;

