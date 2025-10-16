import React from 'react';
import { cn } from '../utils/merge';


const Card = ({ padding = 'md', border = 'none', className, children }) => {
  const paddingClass = {
    none: '',
    xs: 'p-2.5',
    sm: 'p-3',
    md: 'p-4',
    lg: 'p-6',
  }[padding];

  const borderClass = {
    none: '',
    default: 'border border-semantic-border-subtle',
  }[border];

  return (
    <div className={cn('flex flex-col bg-white rounded-2xl', paddingClass, borderClass, className)}>{children}</div>
  );
};

export default Card;
