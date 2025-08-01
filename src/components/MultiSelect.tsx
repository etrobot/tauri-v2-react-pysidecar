import React, { useState } from 'react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command';
import { Button } from '@/components/ui/button';
import { Check, ChevronsUpDown } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface MultiSelectOption {
  label: string;
  value: string;
}

interface MultiSelectProps {
  options: MultiSelectOption[];
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  label?: string;
}

const MultiSelect: React.FC<MultiSelectProps> = ({ options, value, onChange, placeholder }) => {
  const [open, setOpen] = useState(false);

  // 处理选项点击
  const handleValueChange = (selected: string) => {
    let newValue = [...value];
    if (newValue.includes(selected)) {
      newValue = newValue.filter(v => v !== selected);
    } else {
      newValue.push(selected);
    }
    console.log('[MultiSelect] handleValueChange 入参', { selected, value, newValue });
    onChange(newValue);
  };

  return (
    <div className="flex flex-col gap-1">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            className={cn(
              'w-full justify-between',
              !value.length && 'text-muted-foreground'
            )}
          >
            {value.length === 0
              ? (placeholder || '请选择')
              : value.length === 1
                ? options.find(o => o.value === value[0])?.label
                : `已选择 ${value.length} 项`}
            <ChevronsUpDown className="opacity-50 ml-2" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-full p-0">
          <Command>
            <div className="flex gap-2 p-2 border-b border-muted bg-muted/50">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  const allValues = options.map(o => o.value);
                  console.log('[MultiSelect] 全选', { allValues });
                  onChange(allValues);
                }}
              >全选</Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  const inverted = options.map(o => o.value).filter(v => !value.includes(v));
                  console.log('[MultiSelect] 反选', { 原value: value, 新value: inverted });
                  onChange(inverted);
                }}
              >反选</Button>
            </div>
            <CommandInput placeholder="搜索..." className="h-9" />
            <CommandList className="max-h-[300px]">
              <CommandEmpty>无匹配项</CommandEmpty>
              <CommandGroup>
                {options.map(option => {
                  const checked = value.includes(option.value);
                  return (
                    <CommandItem
                      value={option.label}
                      key={option.value}
                      onSelect={() => {
                        console.log('[MultiSelect] CommandItem onSelect', { selected: option.value, checked, value });
                        handleValueChange(option.value);
                        // 不关闭弹层
                      }}
                    >
                      <div className="flex items-center w-full">
                        <Check className={cn('mr-2 h-4 w-4', checked ? 'opacity-100' : 'opacity-0')} />
                        {option.label}
                      </div>
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
};

export default MultiSelect;
