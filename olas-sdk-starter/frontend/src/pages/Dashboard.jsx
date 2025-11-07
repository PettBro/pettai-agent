import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../providers/AuthProvider';
import PetStats from '../components/pet/PetStats';
// ChatHistory disabled for now
import Pet from '../components/pet/Pet';
import backgroundMain from '../assets/images/background-3.jpg';
import backgroundOverlay from '../assets/images/background-0.jpg';
import './Dashboard.scss';

// Removed fallback sprite usage; we render layered pet state instead

const Icon = {
	Logout: ({ className = '' }) => (
		<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="currentColor" d="M8 3c-1.11 0-2 .89-2 2v16h12V5c0-1.11-.89-2-2-2zm0 2h8v14H8zm5 6v2h2v-2z" /></svg>
	),
};

const LAYOUT_CONSTANTS = {
	BOTTOM_UI_PADDING: 24,
	BOTTOM_UI_POSITION_DELAY: 400,
};

const LAST_PET_MESSAGES_STORAGE_KEY = 'pett:lastPetMessages';

const Dashboard = () => {
	const { authenticated, logout } = useAuth();
	const navigate = useNavigate();
	const handleLogout = useCallback(async () => {
		try {
			await logout();
		} catch (error) {
			console.error('[Dashboard] Logout failed:', error);
		} finally {
			navigate('/login');
		}
	}, [logout, navigate]);

	const [healthData, setHealthData] = useState(null);
	const [error, setError] = useState(null);
	const [isAnimating, setIsAnimating] = useState(true);
	const [inputMessage, setInputMessage] = useState('');
	// chat history disabled

	const bottomUIRef = useRef(null);
	const bottomUIPositionRef = useRef(0);

	useEffect(() => {
		if (!authenticated) {
			navigate('/login');
		}
	}, [authenticated, navigate]);

	useEffect(() => {
		const timer = setTimeout(() => setIsAnimating(false), 600);
		return () => clearTimeout(timer);
	}, []);

	useEffect(() => {
		let intervalId;
		const fetchHealth = async () => {
			try {
				const res = await fetch('/api/health');
				if (!res.ok) throw new Error(`Health endpoint returned ${res.status}`);
				const data = await res.json();
				setHealthData(data);
				setError(null);
			} catch (err) {
				console.error('[Dashboard] Failed to fetch health data', err);
				setError('Unable to reach your agent right now.');
			}
		};

		fetchHealth();
		intervalId = setInterval(fetchHealth, 5000);
		return () => clearInterval(intervalId);
	}, []);

	useEffect(() => {
		const updateBottomUIPosition = () => {
			if (bottomUIRef.current) {
				const rect = bottomUIRef.current.getBoundingClientRect();
				bottomUIPositionRef.current = rect.height + LAYOUT_CONSTANTS.BOTTOM_UI_PADDING;
			}
		};

		const timer = setTimeout(updateBottomUIPosition, LAYOUT_CONSTANTS.BOTTOM_UI_POSITION_DELAY);
		window.addEventListener('resize', updateBottomUIPosition);

		return () => {
			clearTimeout(timer);
			window.removeEventListener('resize', updateBottomUIPosition);
		};
	}, []);

	const conversation = useMemo(() => {
		if (!healthData?.recent) return [];
		const items = [];

		// Convert timestamps to seconds (Unix timestamp)
		const toSeconds = ts => {
			if (!ts) return Date.now() / 1000;
			if (typeof ts === 'number') {
				// If it's already in seconds (< 10^11), return as is
				// Otherwise convert milliseconds to seconds
				return ts > 1e11 ? ts / 1000 : ts;
			}
			const t = Date.parse(ts);
			return Number.isNaN(t) ? Date.now() / 1000 : t / 1000;
		};

		// Friendly phrases for recent actions
		const actionToPhrase = entry => {
			const t = String(entry?.type || '').toUpperCase();
			switch (t) {
				case 'SHOWER':
					return 'I just took a bath';
				case 'SLEEP':
					return 'I went to sleep and rested';
				case 'THROWBALL':
					return 'I played with the ball';
				case 'RUB':
					return 'I got some pets and rubs';
				case 'CONSUMABLES_USE':
					return 'I used a consumable to feel better';
				case 'CONSUMABLES_BUY':
					return 'I bought a consumable for later';
				case 'HOTEL_CHECK_IN':
					return 'I checked into the hotel';
				case 'HOTEL_CHECK_OUT':
					return 'I checked out of the hotel';
				case 'HOTEL_BUY':
					return 'I upgraded my hotel tier';
				case 'ACCESSORY_USE':
					return 'I used an accessory';
				case 'ACCESSORY_BUY':
					return 'I bought a new accessory';
				default:
					return t ? `I performed an action: ${t}` : 'I did something';
			}
		};

		if (Array.isArray(healthData.recent.openai_prompts)) {
			healthData.recent.openai_prompts.forEach((prompt, index) => {
				if (!prompt?.prompt) return;
				const role = prompt.kind?.includes('user') ? 'user' : 'pet';
				items.push({
					id: `prompt-${index}`,
					sender: role,
					message: prompt.prompt,
					timestamp: toSeconds(prompt.timestamp),
				});
			});
		}

		// Map recent actions into friendly pet chat messages
		if (Array.isArray(healthData.recent.actions)) {
			healthData.recent.actions.forEach((act, index) => {
				items.push({
					id: `action-${index}`,
					sender: 'pet',
					message: actionToPhrase(act),
					timestamp: toSeconds(act.timestamp),
				});
			});
		}

		if (Array.isArray(healthData.recent.sent_messages)) {
			healthData.recent.sent_messages.forEach((msg, index) => {
				const summary = msg?.type
					? `${msg.type}${msg.success === false ? ' (failed)' : ''}`
					: msg?.success === false
						? 'Message failed'
						: 'Message sent';
				items.push({
					id: `sent-${index}`,
					sender: 'pet',
					message: summary,
					timestamp: toSeconds(msg.timestamp),
				});
			});
		}

		return items.sort((a, b) => a.timestamp - b.timestamp);
	}, [healthData?.recent]);

	const recentActions = useMemo(() => {
		if (!Array.isArray(healthData?.recent?.actions)) return [];
		return [...healthData.recent.actions]
			.filter(Boolean)
			.sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0))
			.slice(0, 10);
	}, [healthData?.recent?.actions]);

	const lastPetMessage = [...conversation].reverse().find(msg => msg.sender === 'pet');

	// Local user chat state (appended on top of health-derived conversation)
	const [userChat, setUserChat] = useState([]);

	useEffect(() => {
		if (typeof window === 'undefined' || !lastPetMessage?.message) return;

		const rawTimestamp = lastPetMessage.timestamp;
		let executedAtMs = Date.now();
		if (typeof rawTimestamp === 'number') {
			executedAtMs = rawTimestamp > 1e11 ? rawTimestamp : rawTimestamp * 1000;
		} else if (rawTimestamp) {
			const parsed = Date.parse(rawTimestamp);
			executedAtMs = Number.isNaN(parsed) ? executedAtMs : parsed;
		}

		const entry = {
			id: lastPetMessage.id || `pet-${executedAtMs}`,
			message: lastPetMessage.message,
			executedAt: new Date(executedAtMs).toISOString(),
		};

		try {
			const raw = window.localStorage.getItem(LAST_PET_MESSAGES_STORAGE_KEY);
			let existing = [];
			if (raw) {
				const parsed = JSON.parse(raw);
				if (Array.isArray(parsed)) {
					existing = parsed;
				}
			}
			const withoutCurrent = existing.filter(item => item && item.id !== entry.id);
			const updated = [...withoutCurrent, entry].slice(-50);
			window.localStorage.setItem(LAST_PET_MESSAGES_STORAGE_KEY, JSON.stringify(updated));
		} catch (storageError) {
			console.error('[Dashboard] Failed to persist last pet message', storageError);
		}
	}, [lastPetMessage?.id, lastPetMessage?.message, lastPetMessage?.timestamp]);
	const remainingMessages = 10;
	const canSendMessage = inputMessage.trim().length > 0;

	const allMessages = useMemo(() => {
		return [...conversation, ...userChat].sort((a, b) => a.timestamp - b.timestamp);
	}, [conversation, userChat]);

	// preview messages disabled

	const handleSend = async () => {
		const text = inputMessage.trim();
		if (!text) return;
		const now = Date.now() / 1000; // Convert to seconds
		const userMsg = { id: `u-${now}`, sender: 'user', message: text, timestamp: now };
		const loadingId = `l-${now}`;
		const loadingMsg = { id: loadingId, sender: 'pet', message: '…', timestamp: now + 1, loading: true };
		setUserChat(prev => [...prev, userMsg, loadingMsg]);
		setInputMessage('');

		try {
			const res = await fetch('/api/chat', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ message: text }),
			});
			const data = await res.json().catch(() => ({}));
			const reply = data?.response || 'sorry i cant talk rn';
			setUserChat(prev => prev.map(m => (m.id === loadingId ? { ...m, message: reply, loading: false } : m)));
		} catch (_e) {
			setUserChat(prev => prev.map(m => (m.id === loadingId ? { ...m, message: 'sorry i cant talk rn', loading: false, error: true } : m)));
		}
	};

	const statsSummary = healthData?.pet?.stats ?? {};

	// Normalize pet data for the Pet component: ignore accessories, keep only base-emotion fields
	const petRaw = healthData?.pet ?? null;
	const rawStats = (petRaw && (petRaw.PetStats || petRaw.stats)) || {};
	const petForView = petRaw
		? {
			PetStats: {
				happiness: Number(rawStats.happiness ?? 100),
				health: Number(rawStats.health ?? 100),
				hunger: Number(rawStats.hunger ?? 100),
				hygiene: Number(rawStats.hygiene ?? 100),
				energy: Number(rawStats.energy ?? 100),
			},
			sleeping: Boolean(petRaw?.sleeping),
			dead: Boolean(petRaw?.dead),
		}
		: null;


	return (
		<div
			className="fixed inset-0 z-50 flex flex-col items-center overflow-hidden"
			style={{
				backgroundImage: `url(${backgroundMain})`,
				backgroundRepeat: 'no-repeat',
				backgroundPosition: 'center 10%',
				backgroundSize: 'auto',
				backgroundColor: '#9ab8f6',
			}}
		>

			<div
				className={`fixed inset-0 background-fade ${isAnimating ? 'background-initial' : ''}`}
				style={{
					backgroundImage: `url(${backgroundOverlay})`,
					backgroundSize: 'cover',
					backgroundPosition: 'center',
					zIndex: 1,
				}}
			/>

			<button
				type="button"
				onClick={handleLogout}
				className="absolute top-4 left-4 z-50 text-white hover:text-gray-100 transition-colors bg-red-600/90 hover:bg-red-700 rounded-full p-2 fade-in-delayed shadow-lg"
				style={{ zIndex: 100 }}
				aria-label="Log out"
				title="Log out"
			>
				<Icon.Logout className="size-6" />
			</button>


			<div
				className="flex-1 flex flex-col items-center relative px-4 pb-32 w-full"
				style={{
					minHeight: '100vh',
					overflow: 'visible',
					paddingTop: '12px',
					zIndex: 10,
				}}
			>
				<div className={`stats-fade-in ${isAnimating ? 'stats-initial' : ''}`}>
					<PetStats stats={statsSummary} />
				</div>

				<div className="chat-shell flex flex-col items-center">
					<div
						className={`relative mb-4 ${isAnimating ? 'pet-scale-initial' : 'pet-scale-final'}`}
						style={{
							minHeight: '280px',
							width: '100%',
							maxWidth: '400px',
							transform: isAnimating ? 'scale(1) translateY(0)' : `scale(1.3) translateY(${bottomUIPositionRef.current}px)`,
							transition: 'transform 0.8s cubic-bezier(0.34, 1.56, 0.64, 1)',
							opacity: 1,
						}}
					>
						<div className="flex flex-col items-center justify-center" style={{ height: '230px', width: '230px', margin: '0 auto' }}>
							<Pet pet={petForView} size="big" />
						</div>
					</div>


					{/* lastPetMessage && (
						<div
							className={`bubble-container bubble-fade-in ${isAnimating ? 'bubble-initial' : ''}`}
							style={{
								left: '50%',
								transform: 'translateX(-50%)',
								top: '280px',
								position: 'absolute',
								zIndex: 10,
								width: 'calc(100% - 40px)',
								maxWidth: '360px',
							}}
						>
							<ChatPreviewMessage message={lastPetMessage} />
						</div>
					) */}
				</div>
			</div>

			<div
				ref={bottomUIRef}
				className={`absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/60 via-black/40 to-transparent backdrop-blur-sm p-6 slide-up ${isAnimating ? 'slide-up-initial' : ''}`}
				style={{
					zIndex: 50,
					background:
						'linear-gradient(to top, rgba(0,0,0,0.6) 0%, rgba(0,0,0,0.4) 30%, rgba(0,0,0,0.2) 60%, transparent 100%)',
					backdropFilter: 'blur(8px)',
					WebkitBackdropFilter: 'blur(8px)',
				}}
			>
				<div className="chat-shell space-y-4">
					<div className="flex flex-col gap-4">
						<div className="flex items-center gap-2 text-xs font-semibold text-emerald-500">
							<span className="inline-flex h-2 w-2 rounded-full bg-emerald-400 animate-pulse" aria-hidden="true" />
							Agent is running
						</div>

						{/* <div className="flex gap-2 items-stretch">
							<div className="flex-1 bg-white/90 backdrop-blur-sm rounded-2xl shadow-lg overflow-hidden">
								<textarea
									className="w-full px-5 py-4 text-gray-800 outline-none bg-transparent resize-none"
									placeholder="Type your message..."
									value={inputMessage}
									onChange={e => setInputMessage(e.target.value)}
									disabled={false}
									rows={2}
								/>
								{remainingMessages < 5 && (
									<div className="px-5 pb-2 text-xs text-gray-500">{remainingMessages} messages remaining</div>
								)}
							</div>

							<button
								type="button"
								disabled={!canSendMessage}
								className="bg-purple-600 hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-white rounded-2xl px-4 py-2 shadow-lg transition-all flex items-center justify-center"
								aria-label="Send message"
								onClick={handleSend}
							>
								<svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
								</svg>
							</button>
						</div> */}
					</div>
				</div>
			</div>

			<style>{`
        .chat-shell {
          width: 100%;
          max-width: 420px;
          margin: 0 auto;
        }
        .background-fade {
          transition: opacity 0.6s ease-out;
        }
        .background-initial {
          opacity: 0;
        }
        .pet-scale-initial {
          transform: scale(1) translateY(0);
          opacity: 1 !important;
        }
        .pet-scale-final {
          transform: scale(1.3);
          opacity: 1 !important;
          transition: transform 0.8s cubic-bezier(0.34, 1.56, 0.64, 1);
        }
        .bubble-container {
          display: flex;
          justify-content: center;
        }
        .bubble-fade-in {
          animation: bubble-fade-in 0.6s ease-out 0.5s both;
        }
        .bubble-initial {
          opacity: 0;
          transform: translateY(-20px) scale(0.95);
        }
        .stats-fade-in {
          animation: stats-fade-in 0.5s ease-out 0.2s both;
        }
        .stats-initial {
          opacity: 0;
          transform: translateY(-6px) scale(0.98);
        }
        @keyframes stats-fade-in {
          from {
            opacity: 0;
            transform: translateY(-6px) scale(0.98);
          }
          to {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }
        @keyframes bubble-fade-in {
          from {
            opacity: 0;
            transform: translateY(-20px) scale(0.95);
          }
          to {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }
        .slide-up {
          transition: transform 0.8s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.8s ease-out;
          mask: linear-gradient(to top, black 0%, black 80%, transparent 100%);
          -webkit-mask: linear-gradient(to top, black 0%, black 80%, transparent 100%);
        }
        .slide-up-initial {
          opacity: 0;
          transform: translateY(100%);
        }
        .fade-in-delayed {
          animation: fade-in-delayed 0.4s ease-out 0.6s both;
        }
        @keyframes fade-in-delayed {
          from {
            opacity: 0;
            transform: scale(0.9);
          }
          to {
            opacity: 1;
            transform: scale(1);
          }
        }
        .animate-history-expand {
          animation: history-expand 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
        }
        @keyframes history-expand {
          from {
            opacity: 0;
            transform: translateY(-10px) scale(0.98);
          }
          to {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }
        @keyframes slide-up-history {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        .animate-slide-up {
          animation: slide-up-history 0.3s ease-out;
        }
      `}</style>
		</div>
	);
};

export default Dashboard;