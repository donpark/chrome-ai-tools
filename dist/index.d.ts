export interface PromptOptions {
    system?: string;
    user: string;
}
export declare function prompt(opts: PromptOptions): Promise<string>;
export declare function summarize(text: string): Promise<string>;
export declare function translate(text: string, sourceLanguage: string, targetLanguage: string): Promise<string>;
export declare function write(text: string, context?: string): Promise<string>;
