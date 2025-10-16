import React, { useEffect, useState } from 'react';
import { useAuth } from '../providers/AuthProvider';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/Button';
import './Dashboard.scss';

const Dashboard = () => {
	const { authenticated, logout } = useAuth();
	const navigate = useNavigate();
	const [healthData, setHealthData] = useState(null);
	const [error, setError] = useState(null);

	useEffect(() => {
		if (!authenticated) {
			navigate('/login');
		}
	}, [authenticated, navigate]);

	useEffect(() => {
		let intervalId;
		const fetchHealth = async () => {
			try {
				const res = await fetch('/api/health');
				const data = await res.json();
				setHealthData(data);
				setError(null);
			} catch (e) {
				setError('Failed to load health data');
			}
		};

		fetchHealth();
		intervalId = setInterval(fetchHealth, 5000);
		return () => clearInterval(intervalId);
	}, []);

	const formatTime = (isoString) => {
		if (!isoString) return 'N/A';
		return new Date(isoString).toLocaleTimeString();
	};

	const formatDate = (isoString) => {
		if (!isoString) return 'N/A';
		return new Date(isoString).toLocaleString();
	};

	return (
		<div className="min-h-screen bg-global-grey-10 p-6">
			{/* Header */}
			<header className="mb-8 flex justify-between items-center">
				<h1 className="text-3xl font-bold text-semantic-fg-base">🐾 Pett Agent Dashboard</h1>
				<Button.Danger size="sm" fullWidth={false} onClick={logout}>
					Logout
				</Button.Danger>
			</header>

			{error && (
				<div className="mb-4 p-4 bg-global-red-10 text-semantic-fg-error rounded-lg">
					{error}
				</div>
			)}

			{!healthData ? (
				<div className="text-center py-12">
					<div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-global-brand-60 border-t-transparent"></div>
					<p className="mt-4 text-semantic-fg-muted">Loading dashboard...</p>
				</div>
			) : (
				<div>
					{/* Pet Stats - Top Card */}
					{healthData.pet?.stats && (
						<div className="bg-white rounded-lg shadow p-6 mb-6">
							<h2 className="text-xl font-bold mb-4 text-semantic-fg-base">Pet Stats</h2>
							<div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
								<div className="flex items-center gap-2"><span>🍔</span><span className="text-semantic-fg-muted">Hunger</span><span className="font-semibold">{healthData.pet.stats.hunger}</span></div>
								<div className="flex items-center gap-2"><span>❤️</span><span className="text-semantic-fg-muted">Health</span><span className="font-semibold">{healthData.pet.stats.health}</span></div>
								<div className="flex items-center gap-2"><span>⚡</span><span className="text-semantic-fg-muted">Energy</span><span className="font-semibold">{healthData.pet.stats.energy}</span></div>
								<div className="flex items-center gap-2"><span>😊</span><span className="text-semantic-fg-muted">Happiness</span><span className="font-semibold">{healthData.pet.stats.happiness}</span></div>
								<div className="flex items-center gap-2"><span>🧼</span><span className="text-semantic-fg-muted">Hygiene</span><span className="font-semibold">{healthData.pet.stats.hygiene}</span></div>
								<div className="flex items-center gap-2"><span>🎯</span><span className="text-semantic-fg-muted">XP</span><span className="font-semibold">{healthData.pet.stats.xp} (Lvl {healthData.pet.stats.level ?? 1})</span></div>
							</div>
						</div>
					)}

					<div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
						{/* System Status Card */}
						<div className="bg-white rounded-lg shadow p-6">
							<h2 className="text-xl font-bold mb-4 text-semantic-fg-base">System Status</h2>
							<div className="space-y-3">
								<div className="flex justify-between">
									<span className="text-semantic-fg-muted">Status:</span>
									<span className={`font-semibold ${healthData.status === 'running' ? 'text-semantic-fg-success' : 'text-semantic-fg-error'}`}>
										{healthData.status}
									</span>
								</div>
								<div className="flex justify-between">
									<span className="text-semantic-fg-muted">Last Transition:</span>
									<span className="font-semibold">{healthData.seconds_since_last_transition?.toFixed(2)}s ago</span>
								</div>
								<div className="flex justify-between">
									<span className="text-semantic-fg-muted">Transitioning Fast:</span>
									<span className="font-semibold">{healthData.is_transitioning_fast ? '⚡ Yes' : 'No'}</span>
								</div>
								<div className="flex justify-between">
									<span className="text-semantic-fg-muted">Withdrawal Mode:</span>
									<span className="font-semibold">{healthData.withdrawal_mode ? 'Yes' : 'No'}</span>
								</div>
								<div className="flex justify-between">
									<span className="text-semantic-fg-muted">Last Updated:</span>
									<span className="font-semibold text-sm">{formatTime(healthData.timestamp)}</span>
								</div>
							</div>
						</div>

						{/* WebSocket Status Card */}
						<div className="bg-white rounded-lg shadow p-6">
							<h2 className="text-xl font-bold mb-4 text-semantic-fg-base">WebSocket Connection</h2>
							<div className="space-y-3">
								<div className="flex justify-between">
									<span className="text-semantic-fg-muted">URL:</span>
									<span className="font-semibold text-sm truncate ml-2">{healthData.websocket?.url}</span>
								</div>
								<div className="flex justify-between">
									<span className="text-semantic-fg-muted">Connected:</span>
									<span className={`font-semibold ${healthData.websocket?.connected ? 'text-semantic-fg-success' : 'text-semantic-fg-error'}`}>
										{healthData.websocket?.connected ? '🟢 Yes' : '🔴 No'}
									</span>
								</div>
								<div className="flex justify-between">
									<span className="text-semantic-fg-muted">Authenticated:</span>
									<span className={`font-semibold ${healthData.websocket?.authenticated ? 'text-semantic-fg-success' : 'text-semantic-fg-error'}`}>
										{healthData.websocket?.authenticated ? '✅ Yes' : '❌ No'}
									</span>
								</div>
								<div className="flex justify-between">
									<span className="text-semantic-fg-muted">Last Activity:</span>
									<span className="font-semibold">{healthData.websocket?.last_activity_seconds_ago?.toFixed(2)}s ago</span>
								</div>
							</div>
						</div>

						{/* Pet Information Card */}
						<div className="bg-white rounded-lg shadow p-6">
							<h2 className="text-xl font-bold mb-4 text-semantic-fg-base">Pet Information</h2>
							{healthData.pet ? (
								<div className="space-y-3">
									<div className="flex justify-between">
										<span className="text-semantic-fg-muted">Name:</span>
										<span className="font-bold text-global-brand-60">{healthData.pet.name}</span>
									</div>
									<div className="flex justify-between">
										<span className="text-semantic-fg-muted">Status:</span>
										<span className={`font-semibold ${healthData.pet.status === 'Active' ? 'text-semantic-fg-success' : 'text-semantic-fg-muted'}`}>
											{healthData.pet.status}
										</span>
									</div>
									<div className="flex justify-between">
										<span className="text-semantic-fg-muted">Balance:</span>
										<span className="font-bold text-global-green-60">{healthData.pet.balance} $AIP</span>
									</div>
									<div className="flex justify-between">
										<span className="text-semantic-fg-muted">Hotel Tier:</span>
										<span className="font-semibold">{healthData.pet.hotel_tier}</span>
									</div>
									<div className="flex justify-between">
										<span className="text-semantic-fg-muted">Sleeping:</span>
										<span className="font-semibold">{healthData.pet.sleeping ? '😴 Yes' : 'No'}</span>
									</div>
									<div className="flex justify-between">
										<span className="text-semantic-fg-muted">Dead:</span>
										<span className="font-semibold">{healthData.pet.dead ? '💀 Yes' : '✅ No'}</span>
									</div>
									<div className="text-xs text-semantic-fg-subtle mt-2">
										ID: {healthData.pet.id}
									</div>
								</div>
							) : (
								<div className="flex flex-col items-center justify-center py-8">
									<div className="inline-block animate-spin rounded-full h-10 w-10 border-4 border-global-brand-60 border-t-transparent mb-3"></div>
									<p className="text-semantic-fg-muted">Loading pet information...</p>
								</div>
							)}
						</div>

						{/* Action Scheduling Card */}
						{healthData.action_scheduling && (
							<div className="bg-white rounded-lg shadow p-6">
								<h2 className="text-xl font-bold mb-4 text-semantic-fg-base">Action Scheduling</h2>
								<div className="space-y-3">
									<div className="flex justify-between">
										<span className="text-semantic-fg-muted">Action Interval:</span>
										<span className="font-semibold">{healthData.action_scheduling.action_interval_minutes} min</span>
									</div>
									<div className="flex justify-between">
										<span className="text-semantic-fg-muted">Next Action:</span>
										<span className="font-semibold text-sm">{formatTime(healthData.action_scheduling.next_action_at)}</span>
									</div>
									<div className="flex justify-between">
										<span className="text-semantic-fg-muted">Minutes Until:</span>
										<span className="font-semibold">{healthData.action_scheduling.minutes_until_next_action} min</span>
									</div>
									<div className="flex justify-between">
										<span className="text-semantic-fg-muted">Scheduled:</span>
										<span className={`font-semibold ${healthData.action_scheduling.next_action_scheduled ? 'text-semantic-fg-success' : 'text-semantic-fg-error'}`}>
											{healthData.action_scheduling.next_action_scheduled ? '✅ Yes' : '❌ No'}
										</span>
									</div>
								</div>
							</div>
						)}

						{/* Recent Actions Card */}
						<div className="bg-white rounded-lg shadow p-6 lg:col-span-2">
							<h2 className="text-xl font-bold mb-4 text-semantic-fg-base">Recent Actions</h2>
							<div className="overflow-x-auto">
								{healthData.recent?.actions?.length > 0 ? (
									<table className="w-full">
										<thead>
											<tr className="border-b border-semantic-border-subtle">
												<th className="text-left py-2 px-3 text-semantic-fg-muted">Time</th>
												<th className="text-left py-2 px-3 text-semantic-fg-muted">Type</th>
												<th className="text-left py-2 px-3 text-semantic-fg-muted">Status</th>
												<th className="text-left py-2 px-3 text-semantic-fg-muted">Pet Stats</th>
											</tr>
										</thead>
										<tbody>
											{healthData.recent.actions.reverse().slice(0, 10).map((action, idx) => (
												<tr key={idx} className="border-b border-semantic-border-subtle hover:bg-global-grey-10">
													<td className="py-2 px-3 text-sm">{formatTime(action.timestamp)}</td>
													<td className="py-2 px-3 font-semibold text-global-brand-60">{action.type}</td>
													<td className="py-2 px-3">{action.success ? '✅' : '❌'}</td>
													<td className="py-2 px-3 text-xs text-semantic-fg-subtle">
														{action.pet_stats && Object.values(action.pet_stats).some(v => v !== null) ? (
															<div className="flex gap-2">
																{action.pet_stats.hunger !== null && <span>🍔 {action.pet_stats.hunger}</span>}
																{action.pet_stats.health !== null && <span>❤️ {action.pet_stats.health}</span>}
																{action.pet_stats.energy !== null && <span>⚡ {action.pet_stats.energy}</span>}
																{action.pet_stats.happiness !== null && <span>😊 {action.pet_stats.happiness}</span>}
																{action.pet_stats.hygiene !== null && <span>🧼 {action.pet_stats.hygiene}</span>}
															</div>
														) : (
															<span className="text-semantic-fg-disabled">-</span>
														)}
													</td>
												</tr>
											))}
										</tbody>
									</table>
								) : (
									<p className="text-semantic-fg-muted">No recent actions</p>
								)}
							</div>
						</div>

						{/* Recent Messages Card */}
						{healthData.recent?.sent_messages?.length > 0 && (
							<div className="bg-white rounded-lg shadow p-6 lg:col-span-2">
								<h2 className="text-xl font-bold mb-4 text-semantic-fg-base">Recent Messages</h2>
								<div className="space-y-2 max-h-64 overflow-y-auto">
									{healthData.recent.sent_messages.reverse().slice(0, 10).map((msg, idx) => (
										<div key={idx} className="p-3 bg-global-grey-10 rounded border border-semantic-border-subtle">
											<div className="flex justify-between items-center">
												<span className="font-semibold text-global-brand-60">{msg.type}</span>
												<span className="text-sm text-semantic-fg-subtle">{formatTime(msg.timestamp)}</span>
											</div>
											{msg.success && <span className="text-xs text-semantic-fg-success">✅ Success</span>}
										</div>
									))}
								</div>
							</div>
						)}

						{/* OpenAI Prompts Card */}
						{healthData.recent?.openai_prompts?.length > 0 && (
							<div className="bg-white rounded-lg shadow p-6 lg:col-span-2">
								<h2 className="text-xl font-bold mb-4 text-semantic-fg-base">AI Decision History</h2>
								<div className="space-y-3">
									{healthData.recent.openai_prompts.slice(0, 5).map((prompt, idx) => (
										<div key={idx} className="p-4 bg-global-blue-10 rounded border border-global-blue-20">
											<div className="flex justify-between items-start mb-2">
												<span className="font-semibold text-global-brand-60 capitalize">{prompt.kind.replace('_', ' ')}</span>
												<span className="text-sm text-semantic-fg-subtle">{formatTime(prompt.timestamp)}</span>
											</div>
											<p className="text-sm text-semantic-fg-muted whitespace-pre-wrap line-clamp-3">{prompt.prompt}</p>
										</div>
									))}
								</div>
							</div>
						)}
					</div>
				</div>
			)}
		</div>
	);
};

export default Dashboard;

