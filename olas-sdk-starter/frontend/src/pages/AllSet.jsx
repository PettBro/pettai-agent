import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../providers/AuthProvider';
import Button from '../components/ui/Button';

const AllSet = () => {
	const { authenticated, logout } = useAuth();
	const navigate = useNavigate();

	const handleLogout = async () => {
		await logout();
		navigate('/login', { replace: true });
	}

	const handleDashboard = () => {
		navigate('/dashboard', { replace: true });
	}

	useEffect(() => {
		if (!authenticated) {
			console.log('Not authenticated, navigating to login');
			navigate('/login', { replace: true });
		}
	}, [authenticated, navigate]);

	return (
		<div className="h-dvh w-full flex flex-col items-center justify-center text-center px-6">
			<h1 className="text-3xl mb-4">All set! 🎉</h1>
			<p className="text-base text-gray-700 max-w-sm">
				You're logged in. You can close this window now and continue using
				your Pett Agent.
			</p>

			<Button onClick={handleLogout} className="mb-3">Logout</Button>
			<Button onClick={handleDashboard} className="mb-3">Dashboard</Button>
		</div>
	);
};

export default AllSet;


