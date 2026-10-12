import * as React from "react";
import { cn } from "@/lib/utils";

// Standard shadcn table primitive — hairline row borders + muted uppercase-ish
// head, matching DESIGN.md's data-table rules. Shared by Agents, Dissent,
// NewRun, and Settings.

function Table({ className, ...props }: React.ComponentProps<"table">) {
	return (
		<div className="relative w-full overflow-x-auto">
			<table data-slot="table" className={cn("w-full caption-bottom text-sm", className)} {...props} />
		</div>
	);
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
	return <thead data-slot="table-header" className={cn("[&_tr]:border-b [&_tr]:border-border", className)} {...props} />;
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
	return <tbody data-slot="table-body" className={cn("[&_tr:last-child]:border-0", className)} {...props} />;
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
	return (
		<tr
			data-slot="table-row"
			className={cn("border-b border-border/60 transition-colors hover:bg-interactive-hover/40", className)}
			{...props}
		/>
	);
}

function TableHead({ className, ...props }: React.ComponentProps<"th">) {
	return (
		<th
			data-slot="table-head"
			className={cn(
				"h-9 px-2.5 text-left align-middle text-xs font-medium text-muted-foreground whitespace-nowrap",
				className,
			)}
			{...props}
		/>
	);
}

function TableCell({ className, ...props }: React.ComponentProps<"td">) {
	return (
		<td data-slot="table-cell" className={cn("px-2.5 py-2 align-middle whitespace-nowrap", className)} {...props} />
	);
}

export { Table, TableHeader, TableBody, TableRow, TableHead, TableCell };
