export interface PromptOptions {
    system?: string;
    user: string;
}
export declare function prompt(opts: PromptOptions): Promise<string>;
