import React, { memo, useCallback } from 'react';
import { cn } from '../utils/merge';

export const getButtonClasses = (type, size, fullWidth = true, disabled = false) => {
  const typeClasses = {
    base: '',
    primary: 'bg-btn-primary text-white',
    secondary: 'bg-semantic-accent-subtle text-semantic-accent-bold',
    tertiary: 'bg-white text-black border border-semantic-accent-muted',
    transparent: 'bg-transparent text-global-brand-60',
    danger: 'bg-global-red-50 text-white',
    'danger-secondary': 'bg-global-red-20 text-global-red-60',
  }[type];

  const sizeClasses = {
    sm: 'text-sm py-[0.438rem] px-4',
    md: 'text-base py-2.5 px-[1.125rem]',
    lg: 'text-lg py-3 px-5',
  }[size];

  return cn(
    'btn inline-flex font-satoshi rounded-full font-bold items-center justify-center',
    typeClasses,
    sizeClasses,
    fullWidth ? 'd-flex w-full' : '',
    disabled ? 'disabled' : '',
  );
};

const ProcessingIndicator = memo(() => (
  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin mr-2 " />
));
ProcessingIndicator.displayName = 'ProcessingIndicator';

const ButtonElement = React.forwardRef(
  (
    {
      isProcessing = false,
      processingText = 'Processing...',
      fullWidth = true,
      type = 'primary',
      size = 'md',
      disabled = false,
      children,
      className,
      onClick,
      ...props
    },
    ref,
  ) => {
    const handleClick = useCallback(
      (e) => {
        if (!disabled && !isProcessing && onClick) {
          onClick(e);
        }
      },
      [disabled, isProcessing, onClick],
    );

    return (
      <button
        ref={ref}
        disabled={isProcessing || disabled}
        className={cn(getButtonClasses(type, size, fullWidth, disabled), className)}
        onClick={handleClick}
        {...props}
      >
        {isProcessing ? (
          <div className="flex items-center justify-center">
            <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin mr-2"></div>
            {processingText}
          </div>
        ) : (
          children
        )}
      </button>
    );
  },
);
ButtonElement.displayName = 'ButtonElement';

const ButtonBase = memo(props => <ButtonElement {...props} type="base" />);
ButtonBase.displayName = 'ButtonBase';

const ButtonPrimary = memo(props => <ButtonElement {...props} type="primary" />);
ButtonPrimary.displayName = 'ButtonPrimary';

const ButtonSecondary = memo(props => <ButtonElement {...props} type="secondary" />);
ButtonSecondary.displayName = 'ButtonSecondary';

const ButtonTertiary = memo(props => <ButtonElement {...props} type="tertiary" />);
ButtonTertiary.displayName = 'ButtonTertiary';

const ButtonTransparent = memo(props => <ButtonElement {...props} type="transparent" />);
ButtonTransparent.displayName = 'ButtonTransparent';

const ButtonDanger = memo(props => <ButtonElement {...props} type="danger" />);
ButtonDanger.displayName = 'ButtonDanger';

const ButtonDangerSecondary = memo(props => <ButtonElement {...props} type="danger-secondary" />);
ButtonDangerSecondary.displayName = 'ButtonDangerSecondary';

const Button = ButtonElement;

Button.Base = ButtonBase;
Button.Primary = ButtonPrimary;
Button.Secondary = ButtonSecondary;
Button.Tertiary = ButtonTertiary;
Button.Transparent = ButtonTransparent;
Button.Danger = ButtonDanger;
Button.DangerSecondary = ButtonDangerSecondary;

export { Button };
export default Button;
