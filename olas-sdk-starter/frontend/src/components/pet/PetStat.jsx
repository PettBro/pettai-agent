import React, { useState, useEffect, useRef } from 'react';

// Local lightweight Icon set mirroring names from main app
const Icon = {
	Food: () => (
		<svg xmlns="http://www.w3.org/2000/svg" width="20" height="18" viewBox="0 0 20 18" fill="none">
			<path fillRule="evenodd" clipRule="evenodd" d="M16.21 1.287C16.531 1.73642 16.4269 2.36097 15.9775 2.68198L12.9489 4.84525C12.4461 5.20442 12.3861 5.92914 12.8231 6.36609L12.9214 6.46442L16.4569 2.92888C16.8474 2.53836 17.4806 2.53836 17.8711 2.92888C18.2617 3.31941 18.2617 3.95257 17.8711 4.3431L14.3356 7.87863L14.434 7.97699C14.8709 8.41394 15.5956 8.35396 15.9548 7.85112L18.1181 4.82254C18.4391 4.37312 19.0636 4.26903 19.5131 4.59004C19.9625 4.91105 20.0666 5.5356 19.7455 5.98501L17.5823 9.0136C16.5048 10.5221 14.3306 10.7021 13.0197 9.39121L12.9214 9.29284L11.2749 10.9393L16.0783 15.7428C16.4689 16.1333 16.4689 16.7665 16.0783 17.157C15.6878 17.5475 15.0546 17.5475 14.6641 17.157L9.86068 12.3535L5.14321 17.071C4.75269 17.4615 4.11952 17.4615 3.729 17.071C3.33847 16.6805 3.33847 16.0473 3.729 15.6568L8.44647 10.9393L6.88596 9.37883L5.47177 10.7931C5.28424 10.9806 5.02988 11.086 4.76466 11.086C4.49944 11.086 4.24508 10.9806 4.05755 10.7931L1.85352 8.58906C0.331719 7.06726 -0.0455539 4.7424 0.916918 2.81746L1.0418 2.5677C1.18555 2.28019 1.45875 2.07932 1.77604 2.02783C2.09333 1.97634 2.41603 2.08051 2.64333 2.3078L7.59305 7.25749L9.86068 9.52512L11.5072 7.87863L11.4088 7.78031C10.098 6.46946 10.2779 4.2953 11.7865 3.21779L14.815 1.05451C15.2645 0.733499 15.889 0.837591 16.21 1.287Z" fill="currentColor" />
		</svg>
	),
	Health: () => (
		<svg xmlns="http://www.w3.org/2000/svg" width="19" height="18" viewBox="0 0 19 18" fill="none">
			<path d="M5.40015 2C5.40015 0.89543 6.29558 0 7.40015 0H11.4001C12.5047 0 13.4001 0.89543 13.4001 2V5H16.4001C17.5047 5 18.4001 5.89543 18.4001 7V11C18.4001 12.1046 17.5047 13 16.4001 13H13.4001V16C13.4001 17.1046 12.5047 18 11.4001 18H7.40015C6.29558 18 5.40015 17.1046 5.40015 16V13H2.40015C1.29558 13 0.400146 12.1046 0.400146 11V7C0.400146 5.89543 1.29558 5 2.40015 5H5.40015V2Z" fill="currentColor" />
		</svg>
	),
	Power: () => (
		<svg xmlns="http://www.w3.org/2000/svg" width="18" height="22" viewBox="0 0 18 22" fill="none">
			<path fillRule="evenodd" clipRule="evenodd" d="M10.7933 0.565462C11.6239 0.959839 12.0383 1.75496 12.1117 2.64448C12.2214 3.97434 11.9552 5.38624 11.7259 6.6982C11.4988 7.99715 11.5221 7.99978 12.7949 7.99966C13.6765 7.99959 14.4514 7.99952 15.0573 8.09271C15.8872 8.22036 16.6324 8.62429 17.0119 9.394C17.6794 10.7475 16.6815 12.2014 16.0354 13.353C14.8354 15.4916 13.4209 17.4114 11.7416 19.1696C10.9733 19.974 10.2897 20.6972 9.66168 21.131C8.92419 21.6405 8.04215 21.8306 7.20654 21.4339C6.37597 21.0395 5.96155 20.2444 5.88816 19.3549C5.77845 18.025 6.04461 16.6131 6.27398 15.3011C6.49532 14.0351 6.52676 13.9996 5.20495 13.9997C4.32338 13.9997 3.5484 13.9998 2.94252 13.9066C2.11264 13.779 1.36748 13.375 0.987926 12.6053C0.320477 11.2518 1.31835 9.79791 1.96449 8.64636C3.16449 6.50774 4.57894 4.58792 6.2582 2.82974C7.02656 2.02529 7.71017 1.30213 8.33816 0.868308C9.07566 0.358841 9.9577 0.168693 10.7933 0.565462Z" fill="currentColor" />
		</svg>
	),
	Gamepad: () => (
		<svg xmlns="http://www.w3.org/2000/svg" width="23" height="16" viewBox="0 0 23 16" fill="none">
			<path fillRule="evenodd" clipRule="evenodd" d="M8.50655 0.389901C7.88441 0.197774 7.24399 0 6.60012 0C5.10396 0 4.07745 1.54306 3.43057 2.69922C2.6433 4.10626 1.95857 5.94323 1.50502 7.75747C1.05458 9.5593 0.806731 11.4395 0.965248 12.919C1.04387 13.6529 1.23256 14.3913 1.63795 14.9713C2.07933 15.6028 2.75108 16 3.60012 16C5.42123 16 6.78476 14.8434 7.85488 13.9357C7.87808 13.9161 7.90133 13.8963 7.92462 13.8766C8.98434 12.9771 10.1355 12 11.6001 12C13.0647 12 14.2159 12.9771 15.2756 13.8766C15.2989 13.8963 15.3221 13.9161 15.3453 13.9357C16.4154 14.8434 17.7789 16 19.6001 16C20.4492 16 21.1209 15.6028 21.5623 14.9713C21.9677 14.3913 22.1564 13.6529 22.235 12.919C22.3936 11.4395 22.1457 9.55929 21.6952 7.75746C21.2417 5.94322 20.5569 4.10625 19.7697 2.69921C19.1228 1.54307 18.0963 0 16.6001 0C15.9562 0 15.3158 0.19778 14.6936 0.389912C14.5278 0.441118 14.3633 0.491923 14.2003 0.538476C13.3348 0.785763 12.4501 1 11.6001 1C10.7501 1 9.86538 0.785762 8.99985 0.538475C8.83691 0.491919 8.67238 0.441111 8.50655 0.389901ZM8.1001 6C7.82396 6 7.6001 6.22386 7.6001 6.5C7.6001 6.77614 7.82396 7 8.1001 7C8.37624 7 8.6001 6.77614 8.6001 6.5C8.6001 6.22386 8.37624 6 8.1001 6ZM5.6001 6.5C5.6001 5.11929 6.71939 4 8.1001 4C9.48081 4 10.6001 5.11929 10.6001 6.5C10.6001 7.88071 9.48081 9 8.1001 9C6.71939 9 5.6001 7.88071 5.6001 6.5ZM15.1001 4C14.5478 4 14.1001 4.44772 14.1001 5V5.5H13.6001C13.0478 5.5 12.6001 5.94772 12.6001 6.5C12.6001 7.05228 13.0478 7.5 13.6001 7.5H14.1001V8C14.1001 8.55228 14.5478 9 15.1001 9C15.6524 9 16.1001 8.55228 16.1001 8V7.5H16.6001C17.1524 7.5 17.6001 7.05228 17.6001 6.5C17.6001 5.94772 17.1524 5.5 16.6001 5.5H16.1001V5C16.1001 4.44772 15.6524 4 15.1001 4Z" fill="currentColor" />
		</svg>
	),
	Bath: () => (
		<svg xmlns="http://www.w3.org/2000/svg" width="20" height="18" viewBox="0 0 20 18" fill="none">
			<path fillRule="evenodd" clipRule="evenodd" d="M4.99976 3C4.99976 2.44772 5.44747 2 5.99976 2H6.99976V3C6.99976 3.55228 7.44747 4 7.99976 4C8.55204 4 8.99976 3.55228 8.99976 3V2C8.99976 0.895431 8.10433 0 6.99976 0H5.99976C4.3429 0 2.99976 1.34315 2.99976 3V8H1.99976C0.895186 8 -0.000244141 8.89543 -0.000244141 10V11C-0.000244141 13.0621 1.03999 14.8812 2.62434 15.9612L2.29265 16.2929C1.90212 16.6834 1.90212 17.3166 2.29265 17.7071C2.68317 18.0976 3.31634 18.0976 3.70686 17.7071L4.58236 16.8316C5.03681 16.9417 5.51147 17 5.99976 17H13.9998C14.488 17 14.9627 16.9417 15.4171 16.8316L16.2926 17.7071C16.6832 18.0976 17.3163 18.0976 17.7069 17.7071C18.0974 17.3166 18.0974 16.6834 17.7069 16.2929L17.3752 15.9612C18.9595 14.8812 19.9998 13.0621 19.9998 11V10C19.9998 8.89543 19.1043 8 17.9998 8H4.99976V3Z" fill="currentColor" />
		</svg>
	),
};

// Minimal progress bar used under each stat
const Progress = ({ value = 0, size = 'xs', color = 'purple' }) => {
	const pct = Math.max(0, Math.min(100, Math.round(Number(value) || 0)));
	const height = size === 'xs' ? '6px' : size === 'sm' ? '8px' : '10px';
	const colorClass = color === 'green' ? '#22c55e' : '#7c3aed';
	return (
		<div className="w-12 rounded-full overflow-hidden" style={{ background: 'rgba(0,0,0,0.08)', height }}>
			<div style={{ width: `${pct}%`, height, background: colorClass, transition: 'width 400ms ease-in-out' }} />
		</div>
	);
};

// Safe highlight stub (can be wired later)
const highlightedStats = new Set();

const PetStat = ({ type, value }) => {
	const [previousValue, setPreviousValue] = useState(value);
	const [animations, setAnimations] = useState([]);
	const [isPressed, setIsPressed] = useState(false);
	const isInitialLoad = useRef(true);

	const statConfig = {
		hunger: {
			bg: 'bg-global-brand-20',
			text: 'text-global-brand-60',
			colorClass: 'text-global-brand-60',
			badgeBg: 'bg-global-brand-60',
		},
		health: {
			bg: 'bg-global-red-20',
			text: 'text-global-red-60',
			colorClass: 'text-global-red-60',
			badgeBg: 'bg-global-red-60',
		},
		energy: {
			bg: 'bg-global-yellow-20',
			text: 'text-global-yellow-60',
			colorClass: 'text-global-yellow-50',
			badgeBg: 'bg-global-yellow-60',
		},
		happiness: {
			bg: 'bg-global-green-20',
			text: 'text-global-green-60',
			colorClass: 'text-global-green-60',
			badgeBg: 'bg-global-green-60',
		},
		hygiene: {
			bg: 'bg-global-blue-20',
			text: 'text-global-blue-60',
			colorClass: 'text-global-blue-60',
			badgeBg: 'bg-global-blue-60',
		},
	}[type];

	const statClass = `${statConfig.bg} ${statConfig.text}`;

	const handleMouseDown = () => {
		setIsPressed(true);
	};

	const handleMouseUp = () => {
		setIsPressed(false);
	};

	const handleMouseLeave = () => {
		setIsPressed(false);
	};

	useEffect(() => {
		// Skip animation on initial load when data first arrives
		if (isInitialLoad.current) {
			isInitialLoad.current = false;
			setPreviousValue(value);

			return;
		}

		if (previousValue !== value && previousValue !== undefined) {
			const change = Math.round(value) - Math.round(previousValue);

			if (change !== 0) {
				const newAnimation = {
					id: `${type}-${Date.now()}`,
					change,
					color: statConfig.colorClass,
				};

				setAnimations(prev => [...prev, newAnimation]);

				// Remove animation after it completes
				setTimeout(() => {
					setAnimations(prev => prev.filter(a => a.id !== newAnimation.id));
				}, 3500); // Animation duration - increased from 2000ms to 3500ms
			}
		}

		setPreviousValue(value);
	}, [value, previousValue, type, statConfig.colorClass]);

	const isHighlighted = highlightedStats.has(type);

	return (
		<div className="w-12 relative mx-auto">
			<div
				className={`
          size-12 rounded-full flex items-center justify-center mb-2.5 cursor-pointer 
          transition-all duration-300 ease-in-out
          hover:scale-105 
          ${isPressed ? 'scale-95' : ''}
          ${value < 50 ? 'animate-bounce-low-stat' : ''}
          ${isHighlighted ? 'animate-pulse ring-2 ring-red-500 ring-opacity-75 shadow-lg scale-110' : ''}
          ${statClass}
        `}
				onMouseDown={handleMouseDown}
				onMouseUp={handleMouseUp}
				onMouseLeave={handleMouseLeave}
			>
				{type === 'hunger' && <Icon.Food />}
				{type === 'health' && <Icon.Health />}
				{type === 'energy' && <Icon.Power />}
				{type === 'happiness' && <Icon.Gamepad />}
				{type === 'hygiene' && <Icon.Bath />}
			</div>
			<div
				className={`absolute border px-1.5 flex top-0 left-8 items-center rounded-full -translate-x-1/2 -translate-y-1/2 text-xs text-white border-white h-[22px] ${statConfig.badgeBg}`}
			>
				{Math.round(value || 0)}
			</div>
			<Progress value={value} size="xs" color={value >= 90 ? 'green' : 'purple'} />

			{/* Floating change animations */}
			{animations.map(animation => (
				<div
					key={animation.id}
					className={`absolute -top-8 left-1/2 transform -translate-x-1/2 pointer-events-none animate-float-up text-lg font-black ${animation.color}`}
				>
					{Math.round(animation.change) > 0 ? '+' : ''}
					{Math.round(animation.change)}
				</div>
			))}
		</div>
	);
};

export default PetStat;
