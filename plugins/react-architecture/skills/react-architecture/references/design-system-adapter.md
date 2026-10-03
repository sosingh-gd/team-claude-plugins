# Design-System Adapter (making the UI library swappable)

Atoms are the seam between our app and whatever UI library is in use. Everything above atoms (molecules, organisms, templates, features) speaks only our own component API.

## Rules

1. **Only atoms import the vendor library.** Molecules and up import atoms.
2. **Own the prop API.** Define props in `<Atom>.types.ts` using our vocabulary. Don't extend vendor prop types (`extends MuiButtonProps`) and don't spread unknown props into the vendor component — that leaks the vendor API and makes swapping a breaking change everywhere.
3. **Limit variants to what the product uses.** `variant: 'primary' | 'secondary' | 'ghost' | 'danger'`, `size: 'sm' | 'md' | 'lg'`. Map them to vendor values inside the atom.
4. **Native HTML passthrough is fine** for genuinely standard attributes (`type`, `disabled`, `aria-*`, `id`, `name`) — pick them explicitly.
5. **Theme via tokens.** Colors, spacing, radius and typography come from `styles/tokens` (CSS variables). The vendor theme is configured from those tokens in `app/providers/ThemeProvider.tsx`, so a new library re-reads the same tokens.
6. **Complex vendor widgets** (data grid, date picker, select with search) still get an atom or organism wrapper with a reduced, domain-neutral API.

## Example: Button atom

```ts
// components/atoms/Button/Button.types.ts
import type { ReactNode, MouseEventHandler } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps {
  children: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  type?: 'button' | 'submit' | 'reset';
  disabled?: boolean;
  loading?: boolean;
  startIcon?: ReactNode;
  fullWidth?: boolean;
  onClick?: MouseEventHandler<HTMLButtonElement>;
  'aria-label'?: string;
}
```

```tsx
// components/atoms/Button/Button.tsx  (MUI implementation)
import MuiButton from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import type { ButtonProps, ButtonVariant } from './Button.types';

const variantMap: Record<ButtonVariant, { variant: 'contained' | 'outlined' | 'text'; color: 'primary' | 'error' }> = {
  primary: { variant: 'contained', color: 'primary' },
  secondary: { variant: 'outlined', color: 'primary' },
  ghost: { variant: 'text', color: 'primary' },
  danger: { variant: 'contained', color: 'error' },
};

const sizeMap = { sm: 'small', md: 'medium', lg: 'large' } as const;

export function Button({ variant = 'primary', size = 'md', loading, disabled, startIcon, children, ...rest }: ButtonProps) {
  const mapped = variantMap[variant];
  return (
    <MuiButton
      {...mapped}
      size={sizeMap[size]}
      disabled={disabled || loading}
      startIcon={loading ? <CircularProgress size={16} /> : startIcon}
      {...rest}
    >
      {children}
    </MuiButton>
  );
}
```

Switching to shadcn/Radix means rewriting this file only; `Button.types.ts` and every consumer stay unchanged. (`...rest` is safe here because `ButtonProps` is a closed, owned type.)

## Example: DataTable organism

The organism composes atoms (Table primitives, Checkbox, Pagination) and exposes a generic API:

```ts
// components/organisms/DataTable/DataTable.types.ts
import type { ReactNode } from 'react';

export interface DataTableColumn<T> {
  id: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  sortable?: boolean;
  width?: number | string;
  align?: 'left' | 'center' | 'right';
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[];
  getRowId: (row: T) => string;
  loading?: boolean;
  emptyState?: ReactNode;
  sort?: { columnId: string; direction: 'asc' | 'desc' };
  onSortChange?: (sort: { columnId: string; direction: 'asc' | 'desc' }) => void;
  selectable?: boolean;
  selectedIds?: string[];
  onSelectionChange?: (ids: string[]) => void;
  pagination?: { page: number; pageSize: number; total: number; onPageChange: (page: number) => void };
  onRowClick?: (row: T) => void;
}
```

The table is controlled: sorting, selection and paging state live in the consumer (usually a feature hook), so the same organism works with client-side or server-side data. A feature then supplies domain columns:

```tsx
// features/orders/components/OrdersTable/OrdersTable.tsx
const columns: DataTableColumn<Order>[] = [
  { id: 'number', header: 'Order #', cell: (o) => o.number, sortable: true },
  { id: 'status', header: 'Status', cell: (o) => <OrderStatusBadge status={o.status} /> },
  { id: 'total', header: 'Total', cell: (o) => formatCurrency(o.total), align: 'right' },
];
```

## Swap checklist (for when the user changes design systems)

1. Rewrite each atom's `.tsx` against the new library; keep `.types.ts` unchanged.
2. Update `app/providers/ThemeProvider.tsx` to map tokens into the new library's theme.
3. Update the ESLint `no-restricted-imports` pattern to the new package names.
4. Run the atom tests and stories; molecules and above should need no changes. Any that do reveal a leaked vendor dependency to fix.
